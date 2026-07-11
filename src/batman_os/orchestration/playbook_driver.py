"""Vol.II Cap.6/7/9 — driver de orquestração para Missões baseadas em
Playbook (Fase 3 do roadmap de plataforma, `.claude/plans/peaceful-
wondering-hearth.md`, Estágio 3.2).

O gap real que este módulo fecha: nenhum código hoje registra a entrada
de um step IMEDIATAMENTE ANTES de invocá-lo — `cli/scan_command.py`
registra tudo antes do loop de despacho começar, o que só funciona
porque cada Missão ali tem exatamente 1 step. Um step de relatório
consolidado precisa dos `StepResult.output` de suas dependências, que só
existem depois delas terminarem — por isso uma Missão baseada em
Playbook precisa de um driver dedicado, não do de `scan_command.py`.

Loop de despacho é sequencial dentro de cada rodada — não reaproveita
`runtime/dispatcher.py` (Fase 2, Estágio 2.4): aquele assume toda entrada
já registrada antes do despacho começar, não comporta "registrar-então-
invocar por rodada" que este driver precisa. Paralelismo intra-Missão
para Playbooks fica fora de escopo desta fase.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from batman_os.capabilities.operator import Operator
from batman_os.foundation.types import (
    MissionId,
    MissionTypeId,
    OperatorRef,
    TenantId,
    WorkflowRunId,
)
from batman_os.kernel.decision_engine import Decision, DecisionEngine
from batman_os.kernel.mission_runtime import MissionEventType, MissionIntent, MissionRuntime
from batman_os.kernel.planning_engine import RegistroCapacidades, RepositorioPlaybooks, plan
from batman_os.kernel.workflow_engine import WorkflowEngine
from batman_os.learning.knowledge_graph import KnowledgeGraph
from batman_os.learning.mission_reconciliation import reconciliar_missao
from batman_os.orchestration.playbook_step_specs import (
    ConstrutorDeEntrada,
    RelatorioConsolidadoSpec,
)
from batman_os.orchestration.step_invoker import InvocadorDeStepPadrao, TabelaDeEntradasPorStep
from batman_os.runtime.capability_engine import CapabilityRegistry
from batman_os.runtime.execution_engine import ExecutionEngine


class PlaybookNaoResolvido(Exception):
    """Levantada quando nenhum Playbook casou com o `intent` — `plan()`
    devolveu um `ExecutionPlan` sem steps."""


class EspecificacaoDeStepAusente(Exception):
    """Levantada quando um `PlanStep` pronto para despacho não tem
    `ConstrutorDeEntrada` correspondente em `especificacoes_por_indice` —
    erro de autoria do Playbook/chamador, nunca silenciado (mesma
    doutrina de "gap nunca aceito 'para ajustar depois'" do resto do
    Kernel)."""


@dataclass
class ResultadoMissaoPlaybook:
    mission_id: MissionId
    workflow_run_id: WorkflowRunId
    estado_final: str
    achados: list[dict[str, Any]] = field(default_factory=list)
    relatorio: dict[str, Any] | None = None


def executar_missao_via_playbook(
    intent: MissionIntent,
    tipo_missao: MissionTypeId,
    tenant_id: TenantId,
    especificacoes_por_indice: dict[int, ConstrutorDeEntrada],
    *,
    runtime: MissionRuntime,
    registro: RegistroCapacidades,
    registry: CapabilityRegistry,
    decision_engine: DecisionEngine,
    execution_engine: ExecutionEngine,
    operator: Operator,
    operator_ref: OperatorRef,
    repositorio_playbooks: RepositorioPlaybooks,
    grafo_conhecimento: KnowledgeGraph | None = None,
) -> ResultadoMissaoPlaybook:
    """Cria a Missão, resolve o Playbook via `plan(..., repositorio_
    playbooks=...)`, e dirige o `WorkflowEngine` registrando a entrada de
    cada step JUSTO ANTES de invocá-lo — nunca antes, para que um step de
    relatório possa ler `StepResult.output` das suas dependências.

    `grafo_conhecimento` (Fase 4, Estágio 4.2) — opcional, `None` por
    padrão (preserva 100% dos chamadores existentes, mesmo padrão de
    `event_bus=None`/`paralelo=False` já usado nas Fases 2-3): quando
    fornecido, a Missão é reconciliada no Knowledge Graph (Mission
    Graph) após atingir estado terminal, via `reconciliar_missao`."""
    mission = runtime.create(intent, tipo_missao, tenant_id=tenant_id)
    runtime.transition(mission.id, MissionEventType.PLANNING_STARTED)

    plano = plan(
        mission_id=mission.id,
        tenant_id=tenant_id,
        intent=intent,
        registro=registro,
        repositorio_playbooks=repositorio_playbooks,
    )
    if not plano.steps:
        runtime.transition(mission.id, MissionEventType.PLAN_FAILED)
        raise PlaybookNaoResolvido(f"Nenhum Playbook casou com o intent {intent.dados}")
    runtime.transition(mission.id, MissionEventType.PLAN_READY)

    especs_por_step_id = {
        plano.steps[i].id: espec for i, espec in especificacoes_por_indice.items()
    }
    steps_de_relatorio = {
        plano.steps[i].id
        for i, espec in especificacoes_por_indice.items()
        if isinstance(espec, RelatorioConsolidadoSpec)
    }

    runtime.transition(mission.id, MissionEventType.DECIDING_STARTED)
    decisoes: list[Decision] = []
    for ponto in plano.decision_points:
        resultado_resolucao = decision_engine.resolve(ponto, mission.id)
        if resultado_resolucao.decision is not None:
            decisoes.append(resultado_resolucao.decision)
    runtime.transition(mission.id, MissionEventType.DECISIONS_RESOLVED)

    tabela = TabelaDeEntradasPorStep()
    invocador = InvocadorDeStepPadrao(
        execution_engine=execution_engine,
        operator=operator,
        operator_ref=operator_ref,
        capability_registry=registry,
        tabela_entradas=tabela,
        mission_id=mission.id,
        tenant_id=tenant_id,
    )
    workflow = WorkflowEngine(invocador)
    run = workflow.iniciar(mission.id, plano)

    while workflow.get_run(run.id).estado == "running":
        prontos = workflow.passos_prontos(run.id)
        if not prontos:
            break
        for step in prontos:
            espec = especs_por_step_id.get(step.id)
            if espec is None:
                raise EspecificacaoDeStepAusente(str(step.id))
            outputs_dep = {
                r.step_id: r.output
                for r in workflow.get_run(run.id).completed_steps
                if r.step_id in step.depende_de
            }
            tabela.registrar(step.id, espec.construir(outputs_dep))
            workflow.executar_passo(run.id, step)

    estado_final = workflow.get_run(run.id).estado
    if estado_final == "completed":
        runtime.transition(mission.id, MissionEventType.WORKFLOW_COMPLETED)
    elif estado_final == "failed":
        runtime.transition(mission.id, MissionEventType.WORKFLOW_FAILED)

    if grafo_conhecimento is not None:
        reconciliar_missao(mission, decisoes, grafo_conhecimento, playbook_id=plano.source_playbook)

    run_final = workflow.get_run(run.id)
    todos_achados: list[dict[str, Any]] = []
    relatorio: dict[str, Any] | None = None
    for resultado in run_final.completed_steps:
        if resultado.step_id in steps_de_relatorio:
            relatorio = resultado.output
            continue
        todos_achados.extend((resultado.output or {}).get("achados", []))

    return ResultadoMissaoPlaybook(
        mission_id=mission.id,
        workflow_run_id=run.id,
        estado_final=estado_final,
        achados=todos_achados,
        relatorio=relatorio,
    )
