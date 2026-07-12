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
    DecisionOption,
    Evidence,
    MissionId,
    MissionTypeId,
    OperatorRef,
    StepId,
    TenantId,
    WorkflowRunId,
)
from batman_os.kernel.decision_engine import Decision, DecisionEngine
from batman_os.kernel.event_bus import EmissorKernel, EventBus, KernelEvent
from batman_os.kernel.mission_runtime import (
    Mission,
    MissionEventType,
    MissionIntent,
    MissionRuntime,
)
from batman_os.kernel.planning_engine import (
    DecisionPoint,
    ExecutionPlan,
    RegistroCapacidades,
    RepositorioPlaybooks,
    hidratar_plano,
    plan,
)
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


class PlanoNaoPersistido(Exception):
    """Fase 7, Estágio 7.3 — levantada por `retomar_missao_apos_
    escalada()` quando `hidratar_plano()` retorna `None`: a Missão
    escalou sem que `event_bus` tivesse sido passado a `continuar_
    missao_via_playbook()` (Estágio 7.1) — sem o plano concreto
    persistido, não há como retomar sem replanejar (proibido, quebraria
    os `PlanStep.id` já referenciados)."""


@dataclass
class ResultadoMissaoPlaybook:
    """`workflow_run_id`/`decision_pendente` (Fase 7 do roadmap de
    plataforma, `.claude/plans/peaceful-wondering-hearth.md`, Estágio
    7.1) — `workflow_run_id` vira opcional: quando a Missão escala para
    humano ANTES do `WorkflowEngine` ser criado (loop de `decision_
    points`, antes da linha `workflow.iniciar()`), não existe nenhum
    `WorkflowRun` ainda. `decision_pendente` carrega o `DecisionPoint`
    que causou a escalada — o Kernel não persiste isso em lugar nenhum
    (achado de investigação), então é responsabilidade do CHAMADOR
    guardá-lo para poder ecoá-lo de volta num resumo futuro."""

    mission_id: MissionId
    estado_final: str
    workflow_run_id: WorkflowRunId | None = None
    decision_pendente: DecisionPoint | None = None
    achados: list[dict[str, Any]] = field(default_factory=list)
    relatorio: dict[str, Any] | None = None


def _publicar_escalada_pendente(
    event_bus: EventBus, mission_id: MissionId, tenant_id: TenantId, ponto: DecisionPoint
) -> None:
    """Fase 10 do roadmap de plataforma (`.claude/plans/peaceful-
    wondering-hearth.md`, Estágio 10.1) — mesmo padrão de `_publicar_
    plan_created()` (`kernel/planning_engine.py`, Fase 2, Estágio 2.2):
    persiste o `DecisionPoint` que causou a escalada para que `GET /jobs/
    {id}` (`api/routers/jobs.py`) continue mostrando `decision_pendente`
    corretamente mesmo depois de um restart do processo — antes desta
    fase, essa informação só existia no `JobStore` em memória
    (`api/state.py`), perdida a cada restart mesmo com `Mission.estado`
    sobrevivendo via `EventBus`."""
    event_bus.publish(
        KernelEvent(
            mission_id=mission_id,
            tenant_id=tenant_id,
            tipo="HumanEscalationPending",
            emitido_por=EmissorKernel.ORCHESTRATION,
            payload={"decision_pendente": ponto.model_dump(mode="json")},
        )
    )


def hidratar_decisao_pendente(event_bus: EventBus, mission_id: MissionId) -> DecisionPoint | None:
    """Fase 10, Estágio 10.1 — reconstrói o `DecisionPoint` pendente a
    partir do evento `HumanEscalationPending` persistido por
    `_publicar_escalada_pendente()`. Retorna `None` se a Missão nunca
    escalou com `event_bus` fornecido.

    Pega sempre o ÚLTIMO evento desse tipo — seguro porque o driver não
    suporta reescalar dentro da MESMA Missão (`retomar_missao_apos_
    escalada()` não cria um novo `WorkflowRun` para uma Missão que já
    tinha um; e uma Missão só chega a `AwaitingHuman` uma vez por
    `mission_id` neste driver), então só pode existir um escalonamento
    pendente por vez."""
    historia = event_bus.replay(mission_id)
    evento = next((e for e in reversed(historia) if e.tipo == "HumanEscalationPending"), None)
    if evento is None:
        return None
    return DecisionPoint.model_validate(evento.payload["decision_pendente"])


def iniciar_missao_via_playbook(
    intent: MissionIntent,
    tipo_missao: MissionTypeId,
    tenant_id: TenantId,
    *,
    runtime: MissionRuntime,
) -> Mission:
    """Fase 7 do roadmap de plataforma (`.claude/plans/peaceful-
    wondering-hearth.md`), Estágio 7.2 — parte RÁPIDA e síncrona de
    `executar_missao_via_playbook()`, fatorada para que um chamador (ex.:
    handler HTTP) obtenha o `mission_id` real IMEDIATAMENTE, antes de
    submeter o resto da execução (potencialmente lenta) a um pool de
    background. `continuar_missao_via_playbook()` faz o resto."""
    mission = runtime.create(intent, tipo_missao, tenant_id=tenant_id)
    runtime.transition(mission.id, MissionEventType.PLANNING_STARTED, tenant_id)
    return mission


def continuar_missao_via_playbook(
    mission: Mission,
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
    event_bus: EventBus | None = None,
) -> ResultadoMissaoPlaybook:
    """Resolve o Playbook via `plan(..., repositorio_playbooks=...)` para
    uma Missão JÁ CRIADA (ver `iniciar_missao_via_playbook()`), e dirige
    o `WorkflowEngine` registrando a entrada de cada step JUSTO ANTES de
    invocá-lo — nunca antes, para que um step de relatório possa ler
    `StepResult.output` das suas dependências.

    `grafo_conhecimento` (Fase 4, Estágio 4.2) — opcional, `None` por
    padrão (preserva 100% dos chamadores existentes, mesmo padrão de
    `event_bus=None`/`paralelo=False` já usado nas Fases 2-3): quando
    fornecido, a Missão é reconciliada no Knowledge Graph (Mission
    Graph) após atingir estado terminal, via `reconciliar_missao`.

    `event_bus` (Fase 7, Estágio 7.1) — opcional, `None` por padrão
    preserva 100% dos chamadores existentes; repassado a `plan(...,
    event_bus=...)` para persistir o `ExecutionPlan` concreto (Fase 2,
    Estágio 2.2). Sem isso, `hidratar_plano()` sempre retorna `None` para
    Missões criadas por este driver, e `retomar_missao()` (`orchestration/
    mission_resumption.py`) nunca conseguiria retomar uma Missão que
    escalou para humano aqui."""
    intent = mission.intent
    tenant_id = mission.tenant_id

    plano = plan(
        mission_id=mission.id,
        tenant_id=tenant_id,
        intent=intent,
        event_bus=event_bus,
        registro=registro,
        repositorio_playbooks=repositorio_playbooks,
    )
    if not plano.steps:
        runtime.transition(mission.id, MissionEventType.PLAN_FAILED, tenant_id)
        raise PlaybookNaoResolvido(f"Nenhum Playbook casou com o intent {intent.dados}")
    runtime.transition(mission.id, MissionEventType.PLAN_READY, tenant_id)

    especs_por_step_id = {
        plano.steps[i].id: espec for i, espec in especificacoes_por_indice.items()
    }
    steps_de_relatorio = {
        plano.steps[i].id
        for i, espec in especificacoes_por_indice.items()
        if isinstance(espec, RelatorioConsolidadoSpec)
    }

    runtime.transition(mission.id, MissionEventType.DECIDING_STARTED, tenant_id)
    decisoes: list[Decision] = []
    for ponto in plano.decision_points:
        resultado_resolucao = decision_engine.resolve(ponto, mission.id)
        if resultado_resolucao.escalonado_para is not None:
            # Fase 7, Estagio 7.1 — achado de investigacao: antes desta
            # correcao, uma escalada era descartada silenciosamente
            # (decision=None, loop continuava, DECISIONS_RESOLVED disparava
            # incondicionalmente) e o workflow era despachado mesmo assim.
            # A Missao PARA aqui — nenhum WorkflowRun e criado ainda, entao
            # `workflow_run_id` nao existe (ver docstring de
            # ResultadoMissaoPlaybook).
            runtime.transition(mission.id, MissionEventType.ESCALATED_TO_HUMAN, tenant_id)
            if event_bus is not None:
                _publicar_escalada_pendente(event_bus, mission.id, tenant_id, ponto)
            return ResultadoMissaoPlaybook(
                mission_id=mission.id,
                estado_final="awaiting_human",
                decision_pendente=ponto,
            )
        if resultado_resolucao.decision is not None:
            decisoes.append(resultado_resolucao.decision)
    runtime.transition(mission.id, MissionEventType.DECISIONS_RESOLVED, tenant_id)

    return _rodar_workflow_e_coletar(
        mission,
        plano,
        especs_por_step_id,
        steps_de_relatorio,
        decisoes,
        runtime=runtime,
        registry=registry,
        execution_engine=execution_engine,
        operator=operator,
        operator_ref=operator_ref,
        grafo_conhecimento=grafo_conhecimento,
        event_bus=event_bus,
    )


def _rodar_workflow_e_coletar(
    mission: Mission,
    plano: ExecutionPlan,
    especs_por_step_id: dict[StepId, ConstrutorDeEntrada],
    steps_de_relatorio: set[StepId],
    decisoes: list[Decision],
    *,
    runtime: MissionRuntime,
    registry: CapabilityRegistry,
    execution_engine: ExecutionEngine,
    operator: Operator,
    operator_ref: OperatorRef,
    grafo_conhecimento: KnowledgeGraph | None,
    event_bus: EventBus | None,
) -> ResultadoMissaoPlaybook:
    """Fase 7, Estágio 7.3 — fatorado de `continuar_missao_via_playbook()`
    para ser reaproveitado também por `retomar_missao_apos_escalada()`:
    todas as decisões já foram resolvidas (seja pelo `DecisionEngine`
    direto, seja por uma resposta humana ecoada de volta) — daqui em
    diante, cria o `WorkflowEngine` e roda até estado terminal.

    `WorkflowEngine(invocador, event_bus=event_bus)` — achado de
    investigação: antes desta correção, o `WorkflowRun` NUNCA era
    persistido (só o `ExecutionPlan`, via `plan(..., event_bus=...)`,
    Estágio 7.1); sem isso, mesmo com o plano persistido, uma tentativa
    futura de hidratar o `WorkflowRun` a partir do `EventBus` sempre
    retornaria vazio."""
    tabela = TabelaDeEntradasPorStep()
    invocador = InvocadorDeStepPadrao(
        execution_engine=execution_engine,
        operator=operator,
        operator_ref=operator_ref,
        capability_registry=registry,
        tabela_entradas=tabela,
        mission_id=mission.id,
        tenant_id=mission.tenant_id,
    )
    workflow = WorkflowEngine(invocador, event_bus=event_bus)
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
            workflow.executar_passo(run.id, step, mission.tenant_id)

    estado_final = workflow.get_run(run.id).estado
    if estado_final == "completed":
        runtime.transition(mission.id, MissionEventType.WORKFLOW_COMPLETED, mission.tenant_id)
    elif estado_final == "failed":
        runtime.transition(mission.id, MissionEventType.WORKFLOW_FAILED, mission.tenant_id)

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


def retomar_missao_apos_escalada(
    mission: Mission,
    decision_pendente: DecisionPoint,
    especificacoes_por_indice: dict[int, ConstrutorDeEntrada],
    *,
    opcao_escolhida: DecisionOption,
    evidencia: list[Evidence],
    runtime: MissionRuntime,
    registry: CapabilityRegistry,
    decision_engine: DecisionEngine,
    execution_engine: ExecutionEngine,
    operator: Operator,
    operator_ref: OperatorRef,
    event_bus: EventBus,
    grafo_conhecimento: KnowledgeGraph | None = None,
) -> ResultadoMissaoPlaybook:
    """Fase 7, Estágio 7.3 — retoma uma Missão que escalou para humano
    ANTES do `WorkflowEngine` ser criado (único caso que `continuar_
    missao_via_playbook()` produz hoje, ver Estágio 7.1 — o driver não
    suporta escalada NO MEIO de uma execução já em andamento, esse
    cenário nunca acontece aqui). Aplica a decisão humana e continua
    exatamente de onde o loop de `decision_points` parou: cria o
    workflow (agora, pela primeira vez) e roda até estado terminal.

    `event_bus` OBRIGATÓRIO aqui (diferente de `continuar_missao_via_
    playbook`, onde é opcional) — sem ele, o plano nunca teria sido
    persistido (Estágio 7.1) e `hidratar_plano()` sempre retornaria
    `None`; não existe "retomar sem `event_bus`" que faça sentido."""
    decision_engine.resolver_com_resposta_humana(
        decision_pendente, mission.id, opcao_escolhida=opcao_escolhida, evidencia=evidencia
    )
    runtime.transition(mission.id, MissionEventType.ESCALATION_RESOLVED, mission.tenant_id)
    runtime.transition(mission.id, MissionEventType.DECISIONS_RESOLVED, mission.tenant_id)

    plano = hidratar_plano(event_bus, mission.id)
    if plano is None:
        raise PlanoNaoPersistido(
            f"Missao {mission.id} nao tem ExecutionPlan persistido — "
            "impossivel retomar sem o plano concreto (nunca replanejar)"
        )

    especs_por_step_id = {
        plano.steps[i].id: espec for i, espec in especificacoes_por_indice.items()
    }
    steps_de_relatorio = {
        plano.steps[i].id
        for i, espec in especificacoes_por_indice.items()
        if isinstance(espec, RelatorioConsolidadoSpec)
    }

    return _rodar_workflow_e_coletar(
        mission,
        plano,
        especs_por_step_id,
        steps_de_relatorio,
        [],
        runtime=runtime,
        registry=registry,
        execution_engine=execution_engine,
        operator=operator,
        operator_ref=operator_ref,
        grafo_conhecimento=grafo_conhecimento,
        event_bus=event_bus,
    )


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
    event_bus: EventBus | None = None,
) -> ResultadoMissaoPlaybook:
    """Wrapper de conveniência (Fase 7, Estágio 7.2) — `iniciar_missao_
    via_playbook()` + `continuar_missao_via_playbook()` numa única
    chamada, comportamento 100% idêntico ao anterior. Todo chamador
    existente (CLI, endpoint HTTP síncrono) continua usando esta função
    sem mudança nenhuma; só o handler assíncrono da API (que precisa do
    `mission_id` ANTES de submeter a parte lenta a um pool de background)
    usa as duas peças fatoradas separadamente."""
    mission = iniciar_missao_via_playbook(intent, tipo_missao, tenant_id, runtime=runtime)
    return continuar_missao_via_playbook(
        mission,
        especificacoes_por_indice,
        runtime=runtime,
        registro=registro,
        registry=registry,
        decision_engine=decision_engine,
        execution_engine=execution_engine,
        operator=operator,
        operator_ref=operator_ref,
        repositorio_playbooks=repositorio_playbooks,
        grafo_conhecimento=grafo_conhecimento,
        event_bus=event_bus,
    )
