"""Vol.IX Cap.34 — orquestrador real do "scan estático".

Migra `python -m Batman.scan.runner` (o motor legado) para o caminho real
Mission Runtime -> Planning Engine -> Decision Engine -> Workflow Engine ->
Execution Engine -> Operator -> Capability certificada, uma Missão por
(arquivo, regra) de todos os lotes já migrados
(`capabilities/rules/lote_01.py`, `lote_02.py`, ...).

Nota de escala (aceita no Milestone 1, ver plano de migração): 1 Missão por
(arquivo, regra) é correto e honesto, mas caro em repositórios grandes
(potencialmente centenas/milhares de Missões). Extensão natural quando o
foco virar performance: uma Capability que aceita lote de arquivos numa
única invocação.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

from batman_os.capabilities.capability_contract import CapabilityImplementation, certificar
from batman_os.capabilities.operator import (
    ExecutionContext,
    FilesystemAccess,
    NetworkPolicy,
    Operator,
    PermissionSet,
    ResourceLimits,
    SandboxPolicy,
    SideEffectScope,
)
from batman_os.capabilities.rules.lote_01 import SpecDeRegra, carregar_lote_01
from batman_os.capabilities.rules.lote_02 import carregar_lote_02
from batman_os.capabilities.rules.regex_sobre_conteudo import construir_implementacao
from batman_os.cli.descoberta_arquivos import entradas_para_regra
from batman_os.foundation.types import (
    Criticidade,
    EscalationPolicy,
    MissionId,
    MissionTypeId,
    OperatorId,
    OperatorRef,
    Reversibilidade,
    StepId,
    TenantId,
    agora,
)
from batman_os.kernel.decision_engine import DecisionEngine, RespostaLlmCandidata
from batman_os.kernel.event_bus import EventBus
from batman_os.kernel.mission_runtime import (
    MissionEventType,
    MissionIntent,
    MissionRuntime,
)
from batman_os.kernel.planning_engine import DecisionPoint, plan
from batman_os.kernel.workflow_engine import WorkflowEngine
from batman_os.orchestration.implementation_registry import ExecutorViaImplementacoes
from batman_os.orchestration.operator_bridge import OperadorExecutavelAdapter
from batman_os.orchestration.schema_validators import (
    ValidadorContratoSempreAprova,
    ValidadorSchemaEstrutural,
)
from batman_os.orchestration.step_invoker import InvocadorDeStepPadrao, TabelaDeEntradasPorStep
from batman_os.runtime.capability_engine import CapabilityRegistry
from batman_os.runtime.execution_engine import ExecutionEngine
from batman_os.workflow.missions import MissionTypeDefinition, MissionTypeRegistry

TIPO_MISSAO = MissionTypeId("scan-estatico")
TENANT_PADRAO = TenantId("local")


@dataclass
class AchadoScan:
    """Espelha `capabilities.rules.regex_sobre_conteudo.Achado` — a saída
    que o operador vê no terminal."""

    codigo: str
    agente: str
    severidade: str
    categoria: str
    titulo: str
    descricao: str
    causa: str
    remediacao: str
    arquivo: str
    chave: str = ""
    fingerprint: str = ""


@dataclass
class ResultadoScan:
    achados: list[AchadoScan] = field(default_factory=list)

    def contagem_por_severidade(self) -> dict[str, int]:
        contagem: dict[str, int] = {}
        for achado in self.achados:
            contagem[achado.severidade] = contagem.get(achado.severidade, 0) + 1
        return contagem


class _SemConhecimentoAinda:
    """Vol.II Cap.8 — nenhuma regra migrada do Learning Engine (Vol.VI)
    alimenta o Decision Engine ainda para este fluxo; irrelevante na
    prática, já que uma regra determinística sem ambiguidade nunca produz
    um `DecisionPoint` na composição via grafo (Cap.7)."""

    def consultar(self, ponto: DecisionPoint) -> None:
        del ponto
        return None


class _LlmNuncaChamadoNesteFluxo:
    def consultar(self, ponto: DecisionPoint) -> RespostaLlmCandidata:
        del ponto
        raise AssertionError("scan estatico nunca escala para LLM - regra deterministica")


class _ValidadorSempreAprova:
    def validar(self, ponto: DecisionPoint, resposta: object) -> bool:
        del ponto, resposta
        return True


def _registro_tipos() -> MissionTypeRegistry:
    registro = MissionTypeRegistry()
    registro.register(
        MissionTypeDefinition(
            id=TIPO_MISSAO,
            criticality=Criticidade.LOW,
            default_sla=timedelta(hours=1),
            escalation_defaults=EscalationPolicy(
                confidence_threshold=0.8,
                preferred_escalation="human",
                max_llm_retries=1,
                reversibility=Reversibilidade.REVERSIVEL,
            ),
        )
    )
    return registro


def _preparar_capability() -> tuple[CapabilityRegistry, CapabilityImplementation, Operator]:
    """Certifica a Capability genérica de verdade (checklist + testes de
    aceitação + idempotência, Vol.IV Cap.16) e monta o Operador real que a
    executa — uma vez por chamada de `executar_scan`, reaproveitado por
    todas as Missões do lote."""
    implementacao = construir_implementacao()
    contexto_certificacao = ExecutionContext(
        mission_id=MissionId("mission-certificacao"),
        tenant_id=TenantId("tenant-certificacao"),
        step_id=StepId("step-certificacao"),
        deadline=agora(),
    )
    entrada_idempotencia = {
        "caminho": "arquivo-de-certificacao.txt",
        "conteudo": "x",
        "regra": {
            "codigo": "CERT-000",
            "agente": "sistema",
            "severidade": "low",
            "categoria": "certificacao",
            "titulo": "t",
            "causa": "c",
            "remediacao": "r",
            "modo": "arquivo-presente",
        },
    }
    definicao_ativa = certificar(
        implementacao,
        entrada_para_teste_idempotencia=entrada_idempotencia,
        contexto_para_teste_idempotencia=contexto_certificacao,
    )

    registry = CapabilityRegistry()
    registry.register(definicao_ativa)

    operator = Operator(
        operator_id=OperatorId("op-scan"),
        capabilities=[definicao_ativa.id],
        permissions=PermissionSet(
            allowed_actions=[str(definicao_ativa.id)], side_effect_scope=SideEffectScope.READ_ONLY
        ),
        sandbox=SandboxPolicy(
            resource_limits=ResourceLimits(),
            network_policy=NetworkPolicy.NONE,
            filesystem_access=FilesystemAccess.NONE,
        ),
        executor=ExecutorViaImplementacoes({definicao_ativa.id: implementacao}),
    )
    return registry, implementacao, operator


def executar_scan(root: Path, especificacoes: list[SpecDeRegra] | None = None) -> ResultadoScan:
    """Vol.IX Cap.34 — roda as Capabilities migradas contra `root`. Sem
    `especificacoes`, usa todos os lotes já migrados (`carregar_lote_01()` +
    `carregar_lote_02()`)."""
    especificacoes = (
        especificacoes if especificacoes is not None else carregar_lote_01() + carregar_lote_02()
    )

    registry, _implementacao, operator = _preparar_capability()
    execution_engine = ExecutionEngine(
        validador_schema=ValidadorSchemaEstrutural(),
        validador_contrato_nao_deterministico=ValidadorContratoSempreAprova(),
    )
    runtime = MissionRuntime(EventBus(), tipos=_registro_tipos())
    decision_engine = DecisionEngine(
        base_conhecimento=_SemConhecimentoAinda(),
        llm_gateway=_LlmNuncaChamadoNesteFluxo(),
        validador=_ValidadorSempreAprova(),
    )
    adapter = OperadorExecutavelAdapter(operator)
    operator_ref = OperatorRef(operator_id=operator.id)

    resultado = ResultadoScan()
    try:
        for item in especificacoes:
            for entrada in entradas_para_regra(root, item["regra"], item["descoberta"]):
                achado = _processar_entrada(
                    entrada.model_dump(),
                    runtime=runtime,
                    registry=registry,
                    decision_engine=decision_engine,
                    execution_engine=execution_engine,
                    adapter=adapter,
                    operator_ref=operator_ref,
                )
                if achado is not None:
                    resultado.achados.append(achado)
    finally:
        execution_engine.fechar()
    return resultado


def _processar_entrada(
    entrada: dict[str, object],
    *,
    runtime: MissionRuntime,
    registry: CapabilityRegistry,
    decision_engine: DecisionEngine,
    execution_engine: ExecutionEngine,
    adapter: OperadorExecutavelAdapter,
    operator_ref: OperatorRef,
) -> AchadoScan | None:
    """Uma Missão real, do início ao fim, para um único (arquivo, regra)."""
    mission = runtime.create(MissionIntent(dados=entrada), TIPO_MISSAO, tenant_id=TENANT_PADRAO)
    runtime.transition(mission.id, MissionEventType.PLANNING_STARTED)

    plano = plan(
        mission_id=mission.id, tenant_id=TENANT_PADRAO, intent=mission.intent, registro=registry
    )
    if not plano.steps:
        runtime.transition(mission.id, MissionEventType.PLAN_FAILED)
        return None
    runtime.transition(mission.id, MissionEventType.PLAN_READY)

    runtime.transition(mission.id, MissionEventType.DECIDING_STARTED)
    for ponto in plano.decision_points:
        decision_engine.resolve(ponto, mission.id)
    runtime.transition(mission.id, MissionEventType.DECISIONS_RESOLVED)

    tabela = TabelaDeEntradasPorStep()
    tabela.registrar(plano.steps[0].id, entrada)
    invocador = InvocadorDeStepPadrao(
        execution_engine=execution_engine,
        adapter=adapter,
        operator_ref=operator_ref,
        capability_registry=registry,
        tabela_entradas=tabela,
        mission_id=mission.id,
        tenant_id=TENANT_PADRAO,
    )
    workflow = WorkflowEngine(invocador)
    run = workflow.iniciar(mission.id, plano)
    while workflow.get_run(run.id).estado == "running":
        prontos = workflow.passos_prontos(run.id)
        if not prontos:
            break
        workflow.executar_passo(run.id, prontos[0])

    if workflow.get_run(run.id).estado != "completed":
        runtime.transition(mission.id, MissionEventType.WORKFLOW_FAILED)
        return None

    runtime.transition(mission.id, MissionEventType.WORKFLOW_COMPLETED)
    saida = workflow.get_run(run.id).completed_steps[0].output
    if not saida or not saida.get("achados"):
        return None
    return AchadoScan(**saida["achados"][0])
