"""Vol.IX Cap.34 — CLI da missão "Auditar Segurança" (Fase 3 do roadmap de
plataforma, `.claude/plans/peaceful-wondering-hearth.md`, Estágio 3.2).

Amarra o Playbook real (6 checagens já migradas + relatório consolidado)
usando os specs JSON JÁ EXISTENTES (via `carregar_lote_01`/`carregar_
lote_02`/`carregar_especificacoes_dependencias` — sem duplicar nenhum
`RegraSpec` à mão) através dos 2 agregadores genéricos (Estágio 3.1) e do
driver de orquestração (Estágio 3.2).

5 das 6 checagens (secrets em código, chave hardcoded, `.env` sem
gitignore, Dockerfile sem HEALTHCHECK, GitHub Actions com deploy antes de
teste) usam a MESMA Capability agregadora (`regex-sobre-conteudo-de-
arquivo-agregador`) — só o `RegraSpec` embutido muda; a checagem de
dependências usa a outra (`toml-dependencias-agregador`).
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

from batman_os.capabilities.capability_contract import certificar
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
from batman_os.capabilities.rules.agregador_generico import (
    construir_implementacao_agregador_dependencias,
    construir_implementacao_agregador_regex,
)
from batman_os.capabilities.rules.lote_01 import carregar_lote_01
from batman_os.capabilities.rules.lote_02 import carregar_lote_02
from batman_os.capabilities.rules.relatorio_consolidado import (
    construir_implementacao as construir_implementacao_relatorio,
)
from batman_os.capabilities.rules.toml_dependencias_loader import (
    carregar_especificacoes_dependencias,
)
from batman_os.cli.descoberta_arquivos import entradas_dependencias_para_regra, entradas_para_regra
from batman_os.foundation.types import (
    CapabilityId,
    CapabilityRef,
    Criticidade,
    EscalationPolicy,
    HumanReviewRef,
    MissionId,
    MissionTypeId,
    OperatorId,
    OperatorRef,
    PlaybookId,
    Reversibilidade,
    StepId,
    TenantId,
    agora,
)
from batman_os.kernel.decision_engine import DecisionEngine, RespostaLlmCandidata
from batman_os.kernel.event_bus import EventBus
from batman_os.kernel.mission_runtime import MissionIntent, MissionRuntime
from batman_os.kernel.planning_engine import DecisionPoint, PlanStepTemplate
from batman_os.learning.knowledge_graph import KnowledgeGraph
from batman_os.orchestration.implementation_registry import ExecutorViaImplementacoes
from batman_os.orchestration.playbook_driver import (
    ResultadoMissaoPlaybook,
    executar_missao_via_playbook,
)
from batman_os.orchestration.playbook_step_specs import ChecagemDeArquivos, RelatorioConsolidadoSpec
from batman_os.orchestration.schema_validators import (
    ValidadorContratoSempreAprova,
    ValidadorSchemaEstrutural,
)
from batman_os.runtime.capability_engine import CapabilityRegistry
from batman_os.runtime.execution_engine import ExecutionEngine
from batman_os.workflow.missions import MissionTypeDefinition, MissionTypeRegistry
from batman_os.workflow.playbooks import (
    FieldCondition,
    IntentMatcher,
    PlaybookDefinition,
    PlaybookProvenance,
    PlaybookRegistry,
    StatusPlaybook,
)

TIPO_MISSAO = MissionTypeId("security-audit")
TENANT_PADRAO = TenantId("local")
PLAYBOOK_ID = PlaybookId("auditoria-seguranca")
CAP_REGEX_AGREGADOR = CapabilityId("regex-sobre-conteudo-de-arquivo-agregador")
CAP_DEPENDENCIAS_AGREGADOR = CapabilityId("toml-dependencias-agregador")
CAP_RELATORIO = CapabilityId("relatorio-consolidado-de-achados")

_CODIGOS_REGEX = ["CLOUD-001", "RED-007", "DEVOPS-003", "CLOUD-002", "DEVOPS-004"]
_CODIGO_DEPENDENCIAS = "DEP-003"


class _SemConhecimentoAinda:
    """Vol.II Cap.8 — nenhuma regra migrada do Learning Engine alimenta o
    Decision Engine ainda para este fluxo; irrelevante na prática, já que
    a composição via grafo (Cap.7) nunca produz `DecisionPoint`."""

    def consultar(self, ponto: DecisionPoint) -> None:
        del ponto
        return None


class _LlmNuncaChamadoNesteFluxo:
    def consultar(self, ponto: DecisionPoint) -> RespostaLlmCandidata:
        del ponto
        raise AssertionError(
            "auditoria de seguranca nunca escala para LLM - regras deterministicas"
        )


class _ValidadorSempreAprova:
    def validar(self, ponto: DecisionPoint, resposta: object) -> bool:
        del ponto, resposta
        return True


def registro_tipos() -> MissionTypeRegistry:
    """Público desde a Fase 6 (`.claude/plans/peaceful-wondering-hearth.md`,
    Estágio 6.1) — reaproveitado pelo app FastAPI (`api/app.py`) para
    construir o `MissionTypeRegistry` uma vez no startup, sem duplicar
    esta lógica."""
    registro = MissionTypeRegistry()
    registro.register(
        MissionTypeDefinition(
            id=TIPO_MISSAO,
            criticality=Criticidade.MEDIUM,
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


def _carregar_specs_regex() -> dict[str, tuple[Any, dict[str, Any]]]:
    todos = carregar_lote_01() + carregar_lote_02()
    por_codigo = {item["regra"].codigo: item for item in todos}
    faltando = [c for c in _CODIGOS_REGEX if c not in por_codigo]
    if faltando:
        raise ValueError(f"Codigos nao encontrados nos lotes carregados: {faltando}")
    return {c: (por_codigo[c]["regra"], por_codigo[c]["descoberta"]) for c in _CODIGOS_REGEX}


def _carregar_spec_dependencias() -> tuple[Any, dict[str, Any]]:
    todos = carregar_especificacoes_dependencias()
    item = next((i for i in todos if i["regra"].codigo == _CODIGO_DEPENDENCIAS), None)
    if item is None:
        raise ValueError(f"Codigo {_CODIGO_DEPENDENCIAS} nao encontrado em toml_dependencias")
    return item["regra"], item["descoberta"]


def montar_playbook(root: Path) -> tuple[PlaybookDefinition, dict[int, Any]]:
    """Monta o Playbook "Auditar Segurança": 6 checagens repo-wide (5 via
    agregador regex + 1 via agregador dependências) + 1 step de relatório
    consolidado dependente de todas.

    Público desde a Fase 6, Estágio 6.1 — chamado POR REQUISIÇÃO pelo app
    FastAPI (barato: os specs estáticos já são carregados por `_carregar_
    specs_regex()`/`_carregar_spec_dependencias()`, o único custo daqui é
    montar `ChecagemDeArquivos` — um dataclass leve, zero I/O na
    construção — com o `root` desta requisição)."""
    specs_regex = _carregar_specs_regex()
    regra_dep, descoberta_dep = _carregar_spec_dependencias()

    steps_template: list[PlanStepTemplate] = []
    especificacoes: dict[int, Any] = {}

    for indice, codigo in enumerate(_CODIGOS_REGEX):
        regra, descoberta = specs_regex[codigo]
        steps_template.append(
            PlanStepTemplate(
                capability=CapabilityRef(capability_id=CAP_REGEX_AGREGADOR, versao="1.0.0")
            )
        )
        especificacoes[indice] = ChecagemDeArquivos(
            root=root,
            regra=regra,
            descoberta=descoberta,
            entradas_para_regra=entradas_para_regra,
            capability_alvo=str(CAP_REGEX_AGREGADOR),
        )

    indice_dep = len(_CODIGOS_REGEX)
    steps_template.append(
        PlanStepTemplate(
            capability=CapabilityRef(capability_id=CAP_DEPENDENCIAS_AGREGADOR, versao="1.0.0")
        )
    )
    especificacoes[indice_dep] = ChecagemDeArquivos(
        root=root,
        regra=regra_dep,
        descoberta=descoberta_dep,
        entradas_para_regra=entradas_dependencias_para_regra,
        capability_alvo=str(CAP_DEPENDENCIAS_AGREGADOR),
    )

    indice_relatorio = indice_dep + 1
    steps_template.append(
        PlanStepTemplate(
            capability=CapabilityRef(capability_id=CAP_RELATORIO, versao="1.0.0"),
            depende_de_indices=list(range(indice_relatorio)),
        )
    )
    especificacoes[indice_relatorio] = RelatorioConsolidadoSpec(
        titulo_missao="Auditoria de Seguranca"
    )

    playbook = PlaybookDefinition(
        id=PLAYBOOK_ID,
        version="1.0.0",
        applies_to=IntentMatcher(
            conditions=[FieldCondition(campo="tipo", operador="eq", valor="security-audit")]
        ),
        mission_type_id=TIPO_MISSAO,
        priority=5,
        steps_template=steps_template,
        provenance=PlaybookProvenance(
            origin="hand-authored", approved_by=HumanReviewRef("review-auditoria-seguranca")
        ),
        status=StatusPlaybook.ACTIVE,
    )
    return playbook, especificacoes


def _contexto_de_certificacao() -> ExecutionContext:
    return ExecutionContext(
        mission_id=MissionId("mission-de-certificacao"),
        tenant_id=TENANT_PADRAO,
        step_id=StepId("step-de-certificacao"),
        deadline=agora(),
    )


def preparar_capabilities() -> tuple[CapabilityRegistry, Operator]:
    """Público desde a Fase 6, Estágio 6.1 — reaproveitado pelo app
    FastAPI para certificar as Capabilities UMA VEZ no startup (custo de
    recertificação pago por processo, não por requisição)."""
    implementacoes = {
        impl.definition.id: impl
        for impl in (
            construir_implementacao_agregador_regex(),
            construir_implementacao_agregador_dependencias(),
            construir_implementacao_relatorio(),
        )
    }

    registry = CapabilityRegistry()
    for capability_id, impl in implementacoes.items():
        definicao_ativa = certificar(
            impl,
            entrada_para_teste_idempotencia=impl.acceptance_tests[0].entrada,
            contexto_para_teste_idempotencia=_contexto_de_certificacao(),
        )
        registry.register(definicao_ativa)
        assert definicao_ativa.id == capability_id

    operator = Operator(
        operator_id=OperatorId("op-auditoria-seguranca"),
        capabilities=list(implementacoes.keys()),
        permissions=PermissionSet(
            allowed_actions=[str(c) for c in implementacoes],
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


def executar_auditoria_seguranca(
    root: Path,
    db_path: str = ":memory:",
    grafo_conhecimento: KnowledgeGraph | None = None,
    tenant_id: TenantId = TENANT_PADRAO,
) -> ResultadoMissaoPlaybook:
    """Vol.IX Cap.34 — roda o Playbook "Auditar Segurança" contra `root`.
    `db_path`: mesma convenção de `cli/scan_command.py::executar_scan`
    (`":memory:"` default; um caminho real persiste os eventos entre
    execuções). `grafo_conhecimento` (Fase 4, Estágio 4.2): opcional,
    repassado direto a `executar_missao_via_playbook` — quando fornecido,
    a Missão é reconciliada no Mission Graph. `tenant_id` (Fase 5,
    Estágio 5.3): opcional, default `TENANT_PADRAO` preserva 100% do
    comportamento atual; CLI: `--tenant`."""
    playbook, especificacoes = montar_playbook(root)
    registry, operator = preparar_capabilities()

    playbook_registry = PlaybookRegistry()
    playbook_registry.register(playbook)

    runtime = MissionRuntime(EventBus(db_path=db_path), tipos=registro_tipos())
    decision_engine = DecisionEngine(
        base_conhecimento=_SemConhecimentoAinda(),
        llm_gateway=_LlmNuncaChamadoNesteFluxo(),
        validador=_ValidadorSempreAprova(),
    )
    execution_engine = ExecutionEngine(
        validador_schema=ValidadorSchemaEstrutural(),
        validador_contrato_nao_deterministico=ValidadorContratoSempreAprova(),
    )
    operator_ref = OperatorRef(operator_id=operator.id)

    try:
        return executar_missao_via_playbook(
            MissionIntent(dados={"tipo": "security-audit"}),
            TIPO_MISSAO,
            tenant_id,
            especificacoes,
            runtime=runtime,
            registro=registry,
            registry=registry,
            decision_engine=decision_engine,
            execution_engine=execution_engine,
            operator=operator,
            operator_ref=operator_ref,
            repositorio_playbooks=playbook_registry,
            grafo_conhecimento=grafo_conhecimento,
        )
    finally:
        execution_engine.fechar()
