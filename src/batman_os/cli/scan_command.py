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

import json
from collections.abc import Sequence
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
from batman_os.capabilities.rules.ast_kwarg_ausente import (
    EntradaKwargAusente,
    RegraKwargAusenteSpec,
)
from batman_os.capabilities.rules.ast_kwarg_ausente import (
    construir_implementacao as construir_implementacao_kwarg_ausente,
)
from batman_os.capabilities.rules.ast_kwarg_ausente_loader import (
    SpecDeRegraKwargAusente,
    carregar_especificacoes_kwarg_ausente,
)
from batman_os.capabilities.rules.ast_padrao_ausente import (
    EntradaAst,
    RegraAstSpec,
)
from batman_os.capabilities.rules.ast_padrao_ausente import (
    construir_implementacao as construir_implementacao_ast,
)
from batman_os.capabilities.rules.ast_padrao_ausente_loader import (
    SpecDeRegraAst,
    carregar_especificacoes_ast,
)
from batman_os.capabilities.rules.execucao_comando_interpretada import (
    EntradaExecucaoComando,
    RegraExecucaoComandoSpec,
)
from batman_os.capabilities.rules.execucao_comando_interpretada import (
    construir_implementacao as construir_implementacao_execucao_comando,
)
from batman_os.capabilities.rules.execucao_comando_interpretada_loader import (
    SpecDeRegraExecucaoComando,
    carregar_especificacoes_execucao_comando,
)
from batman_os.capabilities.rules.git_comando_interpretado import (
    EntradaGitInterpretado,
    RegraComparacaoNumericaSpec,
)
from batman_os.capabilities.rules.git_comando_interpretado import (
    construir_implementacao as construir_implementacao_git,
)
from batman_os.capabilities.rules.git_comando_interpretado_loader import (
    SpecDeRegraGitInterpretado,
    carregar_especificacoes_git_interpretado,
)
from batman_os.capabilities.rules.lote_01 import SpecDeRegra, carregar_lote_01
from batman_os.capabilities.rules.lote_02 import carregar_lote_02
from batman_os.capabilities.rules.regex_sobre_conteudo import EntradaRegexArquivo
from batman_os.capabilities.rules.regex_sobre_conteudo import (
    construir_implementacao as construir_implementacao_regex,
)
from batman_os.cli.descoberta_arquivos import (
    entradas_ast_para_regra,
    entradas_execucao_comando_para_regra,
    entradas_git_interpretado_para_regra,
    entradas_kwarg_ausente_para_regra,
    entradas_para_regra,
)
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


def _capabilities_a_registrar() -> list[tuple[CapabilityImplementation, dict[str, object]]]:
    """Uma entrada por Capability genérica migrada — `(implementação, entrada
    de teste de idempotência)`. Adicionar aqui é o único passo necessário
    para uma nova Skill entrar no scan (registro/Operador/Executor são
    genéricos em `_preparar_capabilities`, não precisam mudar)."""
    return [
        (
            construir_implementacao_regex(),
            {
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
            },
        ),
        (
            construir_implementacao_ast(),
            {
                "caminho": "arquivo-de-certificacao.py",
                "conteudo": "class X:\n    pass\n",
                "regra": {
                    "codigo": "CERT-001",
                    "agente": "sistema",
                    "severidade": "low",
                    "categoria": "certificacao",
                    "titulo": "t",
                    "causa": "c",
                    "remediacao": "r",
                    "seletor_tipo": "classdef",
                    "seletor_include": "X",
                    "corpo_padrao": "protegido",
                },
            },
        ),
        (
            construir_implementacao_kwarg_ausente(),
            {
                "caminho": "arquivo-de-certificacao.py",
                "conteudo": "x = 1\n",
                "regra": {
                    "codigo": "CERT-002",
                    "agente": "sistema",
                    "severidade": "low",
                    "categoria": "certificacao",
                    "titulo": "t",
                    "causa": "c",
                    "remediacao": "r",
                    "metodos_call": ["get"],
                    "kwarg_obrigatorio": "timeout",
                },
            },
        ),
        (
            construir_implementacao_git(),
            {
                "caminho": ".git",
                "conteudo": "3",
                "regra": {
                    "codigo": "CERT-003",
                    "agente": "sistema",
                    "severidade": "low",
                    "categoria": "certificacao",
                    "titulo": "t",
                    "causa": "c",
                    "remediacao": "r",
                    "limiar": 0,
                },
            },
        ),
        (
            construir_implementacao_execucao_comando(),
            {
                "caminho": "tests/",
                "conteudo": json.dumps(
                    {
                        "returncode": 1,
                        "stdout": "1 failed",
                        "stderr": "",
                        "dir_requerido_existe": True,
                    }
                ),
                "regra": {
                    "codigo": "CERT-004",
                    "agente": "sistema",
                    "severidade": "low",
                    "categoria": "certificacao",
                    "titulo": "t",
                    "causa": "c",
                    "remediacao": "r",
                    "interpretacao": "pytest_falhou",
                },
            },
        ),
    ]


def _preparar_capabilities() -> tuple[CapabilityRegistry, Operator]:
    """Certifica as Capabilities genéricas de verdade (checklist + testes de
    aceitação + idempotência, Vol.IV Cap.16) e monta o Operador real que as
    executa — uma vez por chamada de `executar_scan`, reaproveitado por
    todas as Missões do lote. Registra TODAS no mesmo Registry —
    `CapabilityRegistry.find_candidates` (Vol.III Cap.11) já resolve qual
    delas serve cada Missão por casamento estrutural de schema (ver
    docstring de `EntradaAst.tipo`/`EntradaKwargAusente.tipo`), sem código de
    roteamento extra aqui."""
    definicoes: list[CapabilityDefinition] = []
    implementacoes: dict[CapabilityId, CapabilityImplementation] = {}
    for implementacao, entrada_idempotencia in _capabilities_a_registrar():
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


_Especificacao = (
    SpecDeRegra
    | SpecDeRegraAst
    | SpecDeRegraKwargAusente
    | SpecDeRegraGitInterpretado
    | SpecDeRegraExecucaoComando
)


def _todas_especificacoes() -> list[_Especificacao]:
    especificacoes: list[_Especificacao] = []
    especificacoes.extend(carregar_lote_01())
    especificacoes.extend(carregar_lote_02())
    especificacoes.extend(carregar_especificacoes_ast())
    especificacoes.extend(carregar_especificacoes_kwarg_ausente())
    especificacoes.extend(carregar_especificacoes_git_interpretado())
    especificacoes.extend(carregar_especificacoes_execucao_comando())
    return especificacoes


def executar_scan(
    root: Path, especificacoes: Sequence[_Especificacao] | None = None
) -> ResultadoScan:
    """Vol.IX Cap.34 — roda as Capabilities migradas contra `root`. Sem
    `especificacoes`, usa todos os lotes/Skills já migrados
    (`carregar_lote_01()` + `carregar_lote_02()` + `carregar_especificacoes_ast()`
    + `carregar_especificacoes_kwarg_ausente()` +
    `carregar_especificacoes_git_interpretado()` +
    `carregar_especificacoes_execucao_comando()`)."""
    especificacoes = especificacoes if especificacoes is not None else _todas_especificacoes()

    registry, operator = _preparar_capabilities()
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
            regra = item["regra"]
            entradas: Sequence[
                EntradaRegexArquivo
                | EntradaAst
                | EntradaKwargAusente
                | EntradaGitInterpretado
                | EntradaExecucaoComando
            ]
            if isinstance(regra, RegraAstSpec):
                entradas = entradas_ast_para_regra(root, regra, item["descoberta"])
            elif isinstance(regra, RegraKwargAusenteSpec):
                entradas = entradas_kwarg_ausente_para_regra(root, regra, item["descoberta"])
            elif isinstance(regra, RegraComparacaoNumericaSpec):
                entradas = entradas_git_interpretado_para_regra(root, regra, item["descoberta"])
            elif isinstance(regra, RegraExecucaoComandoSpec):
                entradas = entradas_execucao_comando_para_regra(root, regra, item["descoberta"])
            else:
                entradas = entradas_para_regra(root, regra, item["descoberta"])
            for entrada in entradas:
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
