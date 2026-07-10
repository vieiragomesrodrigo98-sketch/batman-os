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

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

from batman_os.capabilities import registry_sdk
from batman_os.capabilities.capability_contract import (
    CapabilityImplementation,
    GapDeChecklist,
    ResultadoEsperado,
    certificar,
)
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
from batman_os.cli.descoberta_arquivos import registrar_capabilities_conhecidas
from batman_os.foundation.types import (
    CapabilityId,
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
from batman_os.runtime.capability_engine import CapabilityDefinition, CapabilityRegistry
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
    duracoes_por_capability: dict[str, list[float]] = field(default_factory=dict)

    def contagem_por_severidade(self) -> dict[str, int]:
        contagem: dict[str, int] = {}
        for achado in self.achados:
            contagem[achado.severidade] = contagem.get(achado.severidade, 0) + 1
        return contagem

    def resumo_de_performance(self) -> dict[str, dict[str, float]]:
        """Fase 1 do roadmap de plataforma ("Capability Timeline") --
        agrega os tempos de execucao por Capability atraves de todas as
        Missoes do scan. Nao adiciona instrumentacao nova: os tempos ja
        sao medidos nativamente por `StepResult.iniciado_em`/
        `finalizado_em` (Vol.II Cap.9) para cada step -- aqui so
        agregamos o que ja existe."""
        resumo: dict[str, dict[str, float]] = {}
        for capability_id, duracoes in self.duracoes_por_capability.items():
            resumo[capability_id] = {
                "chamadas": float(len(duracoes)),
                "total_ms": sum(duracoes),
                "media_ms": sum(duracoes) / len(duracoes),
                "max_ms": max(duracoes),
            }
        return resumo


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


def _certificar_com_idempotencia(
    implementacao: CapabilityImplementation, entrada_idempotencia: dict[str, object]
) -> CapabilityDefinition:
    contexto_certificacao = ExecutionContext(
        mission_id=MissionId("mission-certificacao"),
        tenant_id=TenantId("tenant-certificacao"),
        step_id=StepId("step-certificacao"),
        deadline=agora(),
    )
    return certificar(
        implementacao,
        entrada_para_teste_idempotencia=entrada_idempotencia,
        contexto_para_teste_idempotencia=contexto_certificacao,
    )


def _entrada_de_idempotencia(implementacao: CapabilityImplementation) -> dict[str, object]:
    """Reaproveita o primeiro teste de aceitacao SUCCESS da propria
    Capability como payload do teste de idempotencia (AT-16.3) -- elimina
    o mecanismo antigo de ~46 payloads CERT-NNN hand-crafted em
    `scan_command.py` (Fase 1 do roadmap de plataforma, ver `.claude/
    plans/peaceful-wondering-hearth.md`). Seguro porque toda Capability
    migrada e `side_effects=none` -- repetir a mesma entrada valida
    produz a mesma saida, nao e um caminho especial de teste."""
    for teste in implementacao.acceptance_tests:
        if teste.resultado_esperado == ResultadoEsperado.SUCCESS:
            return dict(teste.entrada)
    raise GapDeChecklist(
        f"Capability '{implementacao.definition.id}' sem teste SUCCESS para "
        "derivar o payload de idempotencia (AT-16.3)"
    )


def _preparar_capabilities() -> tuple[CapabilityRegistry, Operator]:
    """Certifica todas as Capabilities registradas (checklist + testes de
    aceitacao + idempotencia, Vol.IV Cap.16) e monta o Operador real que as
    executa -- uma vez por chamada de `executar_scan`, reaproveitado por
    todas as Missoes do lote. Registra TODAS no mesmo Registry --
    `CapabilityRegistry.find_candidates` (Vol.III Cap.11) ja resolve qual
    delas serve cada Missao por casamento estrutural de schema, sem
    codigo de roteamento extra aqui.

    Fonte das Capabilities: `registry_sdk.registry()`, populado por
    `descoberta_arquivos.py::registrar_capabilities_conhecidas()` -- unico
    ponto de registro necessario para uma Capability nova (Fase 1 do
    roadmap de plataforma)."""
    if not registry_sdk.registry():
        registrar_capabilities_conhecidas()

    definicoes: list[CapabilityDefinition] = []
    implementacoes: dict[CapabilityId, CapabilityImplementation] = {}
    for plugin in registry_sdk.registry().values():
        implementacao = plugin.construir_implementacao()
        entrada_idempotencia = _entrada_de_idempotencia(implementacao)
        definicao = _certificar_com_idempotencia(implementacao, entrada_idempotencia)
        definicoes.append(definicao)
        implementacoes[definicao.id] = implementacao

    registry = CapabilityRegistry()
    for definicao in definicoes:
        registry.register(definicao)

    operator = Operator(
        operator_id=OperatorId("op-scan"),
        capabilities=[definicao.id for definicao in definicoes],
        permissions=PermissionSet(
            allowed_actions=[str(definicao.id) for definicao in definicoes],
            side_effect_scope=SideEffectScope.READ_ONLY,
        ),
        sandbox=SandboxPolicy(
            resource_limits=ResourceLimits(),
            network_policy=NetworkPolicy.NONE,
            filesystem_access=FilesystemAccess.NONE,
        ),
        executor=ExecutorViaImplementacoes(implementacoes),
    )
    return registry, operator


def _todas_especificacoes() -> list[Any]:
    """Concatena os specs de TODAS as Capabilities registradas --
    substitui a lista manual de ~48 `especificacoes.extend(...)` (Fase 1
    do roadmap de plataforma). Cada item mantem o mesmo shape de sempre
    (`{"regra": RegraXSpec, "descoberta": dict}`), sem tag de `tipo` --
    compatibilidade total com quem ja chama
    `executar_scan(especificacoes=carregar_especificacoes_x())`
    diretamente (`tests/cli/test_scan_command.py`)."""
    especificacoes: list[Any] = []
    for plugin in registry_sdk.registry().values():
        especificacoes.extend(plugin.carregar_especificacoes())
    return especificacoes


def executar_scan(
    root: Path,
    especificacoes: Sequence[Any] | None = None,
    db_path: str = ":memory:",
) -> ResultadoScan:
    """Vol.IX Cap.34 -- roda as Capabilities migradas contra `root`. Sem
    `especificacoes`, usa os specs de todas as Capabilities registradas
    (`registry_sdk.registry()`, populado por `descoberta_arquivos.py::
    registrar_capabilities_conhecidas()`).

    `db_path` (Milestone 5 desta construcao): repassado ao `EventBus`
    interno do Mission Runtime -- `":memory:"` (default) preserva o
    comportamento anterior (log descartado ao final do scan); um caminho
    real faz os eventos desta execucao sobreviverem e acumularem entre
    scans sucessivos apontando para o mesmo arquivo (CLI: `--db`)."""
    if not registry_sdk.registry():
        registrar_capabilities_conhecidas()
    especificacoes = especificacoes if especificacoes is not None else _todas_especificacoes()

    registry, operator = _preparar_capabilities()
    dispatch_por_regra = registry_sdk.registry_por_regra_cls()
    execution_engine = ExecutionEngine(
        validador_schema=ValidadorSchemaEstrutural(),
        validador_contrato_nao_deterministico=ValidadorContratoSempreAprova(),
    )
    runtime = MissionRuntime(EventBus(db_path=db_path), tipos=_registro_tipos())
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
            regra = item["regra"]
            plugin = dispatch_por_regra.get(type(regra))
            if plugin is None:
                raise ValueError(
                    f"regra do tipo {type(regra).__name__} nao tem Capability registrada "
                    "(ver descoberta_arquivos.py::registrar_capabilities_conhecidas)"
                )
            entradas = plugin.entradas_para_regra(root, regra, item["descoberta"])
            for entrada in entradas:
                resultado_missao = _processar_entrada(
                    entrada.model_dump(),
                    runtime=runtime,
                    registry=registry,
                    decision_engine=decision_engine,
                    execution_engine=execution_engine,
                    adapter=adapter,
                    operator_ref=operator_ref,
                )
                resultado.achados.extend(resultado_missao.achados)
                if resultado_missao.capability_id is not None and (
                    resultado_missao.duracao_ms is not None
                ):
                    resultado.duracoes_por_capability.setdefault(
                        resultado_missao.capability_id, []
                    ).append(resultado_missao.duracao_ms)
    finally:
        execution_engine.fechar()
    return resultado


@dataclass
class ResultadoMissao:
    """Achados + observabilidade de uma unica Missao (Fase 1 do roadmap
    de plataforma) -- `capability_id`/`duracao_ms` vem direto do
    `StepResult` que o Workflow Engine ja mede nativamente (Vol.II
    Cap.9), sem instrumentacao nova."""

    achados: list[AchadoScan] = field(default_factory=list)
    capability_id: str | None = None
    duracao_ms: float | None = None


def _processar_entrada(
    entrada: dict[str, object],
    *,
    runtime: MissionRuntime,
    registry: CapabilityRegistry,
    decision_engine: DecisionEngine,
    execution_engine: ExecutionEngine,
    adapter: OperadorExecutavelAdapter,
    operator_ref: OperatorRef,
) -> ResultadoMissao:
    """Uma Missão real, do início ao fim, para um único (arquivo, regra).

    Retorna TODOS os achados da Missão, não só o primeiro (achado da
    validação de FE-API: uma Missão pode legitimamente produzir MÚLTIPLOS
    achados — ex.: várias rotas ausentes no mesmo arquivo, cada uma com
    `chave` distinta — `saida["achados"][0]` descartava silenciosamente
    os demais)."""
    mission = runtime.create(MissionIntent(dados=entrada), TIPO_MISSAO, tenant_id=TENANT_PADRAO)
    runtime.transition(mission.id, MissionEventType.PLANNING_STARTED)

    plano = plan(
        mission_id=mission.id, tenant_id=TENANT_PADRAO, intent=mission.intent, registro=registry
    )
    if not plano.steps:
        runtime.transition(mission.id, MissionEventType.PLAN_FAILED)
        return ResultadoMissao()
    runtime.transition(
        mission.id,
        MissionEventType.PLAN_READY,
        payload_extra={"capability_id": str(plano.steps[0].capability.capability_id)},
    )

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
        return ResultadoMissao()

    step_result = workflow.get_run(run.id).completed_steps[0]
    duracao_ms = (step_result.finalizado_em - step_result.iniciado_em).total_seconds() * 1000
    capability_id = str(plano.steps[0].capability.capability_id)
    runtime.transition(
        mission.id,
        MissionEventType.WORKFLOW_COMPLETED,
        payload_extra={"capability_id": capability_id, "duracao_ms": round(duracao_ms, 3)},
    )
    saida = step_result.output
    if not saida or not saida.get("achados"):
        return ResultadoMissao(capability_id=capability_id, duracao_ms=duracao_ms)
    return ResultadoMissao(
        achados=[AchadoScan(**item) for item in saida["achados"]],
        capability_id=capability_id,
        duracao_ms=duracao_ms,
    )
