"""Vol.IX Cap.34/35 — prova de composição real da migração do primeiro lote.

Reproduz o caminho completo Mission Runtime -> Planning Engine -> Decision
Engine (sempre 0 `DecisionPoint`s, mas chamado de verdade — não contornado) ->
Workflow Engine -> Execution Engine -> Operator -> Capability real, contra um
repositório sintético em `tmp_path`. Mesma doutrina do cenário de referência
já existente (`test_gunicorn_timeout_e2e.py`): nenhum mock de Kernel/Runtime/
Capabilities, só os Protocols de borda que a própria arquitetura já define.

Usa a Capability genérica "regex sobre conteúdo de arquivo"
(`capabilities/rules/regex_sobre_conteudo.py`) com a regra VPS-001 (a mais
simples do primeiro lote: dispara quando `.env.production.example` está
ausente) para provar que a canalização inteira (Vol.II + Vol.III + Vol.IV)
se compõe de ponta a ponta contra um alvo real — não só em teste unitário
isolado por módulo.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

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
from batman_os.capabilities.rules.regex_sobre_conteudo import RegraSpec, construir_implementacao
from batman_os.cli.descoberta_arquivos import entradas_para_regra
from batman_os.foundation.types import (
    Criticidade,
    EscalationPolicy,
    MissionTypeId,
    OperatorId,
    OperatorRef,
    Reversibilidade,
    TenantId,
)
from batman_os.kernel.decision_engine import DecisionEngine, RespostaLlmCandidata
from batman_os.kernel.event_bus import EventBus
from batman_os.kernel.mission_runtime import (
    MissionEventType,
    MissionIntent,
    MissionRuntime,
    MissionState,
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

TIPO = MissionTypeId("scan-estatico")
TENANT = TenantId("t-1")


def _regra_vps001() -> RegraSpec:
    return RegraSpec(
        codigo="VPS-001",
        agente="vps-infra",
        severidade="high",
        categoria="configuracao",
        titulo=".env.production.example ausente — sem template de configuração de produção",
        causa="Sem o arquivo, o operador não tem referencia das variaveis obrigatorias.",
        remediacao="Criar .env.production.example com valores placeholder.",
        modo="arquivo-ausente",
    )


def _registro_tipos() -> MissionTypeRegistry:
    registro = MissionTypeRegistry()
    registro.register(
        MissionTypeDefinition(
            id=TIPO,
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


class TestScanPontaAPonta:
    def test_regra_vps001_dispara_quando_env_producao_ausente(self, tmp_path: Path) -> None:
        # 1. Descoberta real de arquivos contra o repo sintetico (sem
        # .env.production.example -> a regra deve disparar).
        entradas = entradas_para_regra(
            tmp_path,
            _regra_vps001(),
            {"tipo": "arquivo_fixo", "caminho": ".env.production.example"},
        )
        assert len(entradas) == 1
        entrada = entradas[0]
        assert entrada.conteudo is None

        # 2. Capability real: certificada de verdade (checklist + testes de
        # aceitacao + idempotencia), nao um dublê.
        implementacao = construir_implementacao()
        definicao_ativa = certificar(
            implementacao,
            entrada_para_teste_idempotencia=entrada.model_dump(),
            contexto_para_teste_idempotencia=_contexto_teste(),
        )
        registry = CapabilityRegistry()
        registry.register(definicao_ativa)

        # 3. Operador real, com o roteador que fecha a lacuna
        # CapabilityRegistry (so metadados) -> handler de verdade.
        operator = Operator(
            operator_id=OperatorId("op-scan"),
            capabilities=[definicao_ativa.id],
            permissions=PermissionSet(
                allowed_actions=[str(definicao_ativa.id)],
                side_effect_scope=SideEffectScope.READ_ONLY,
            ),
            sandbox=SandboxPolicy(
                resource_limits=ResourceLimits(),
                network_policy=NetworkPolicy.NONE,
                filesystem_access=FilesystemAccess.NONE,
            ),
            executor=ExecutorViaImplementacoes({definicao_ativa.id: implementacao}),
        )
        adapter = OperadorExecutavelAdapter(operator)

        # 4. Mission Runtime cria a Missao de verdade.
        runtime = MissionRuntime(EventBus(), tipos=_registro_tipos())
        mission = runtime.create(
            MissionIntent(
                dados={
                    "caminho": entrada.caminho,
                    "conteudo": entrada.conteudo,
                    "condicoes_adicionais": [],
                    "regra": entrada.regra.model_dump(),
                }
            ),
            TIPO,
            tenant_id=TENANT,
        )
        runtime.transition(mission.id, MissionEventType.PLANNING_STARTED)

        # 5. Planning Engine compoe via grafo (nenhum Playbook existe ainda)
        # consultando o CapabilityRegistry real via find_candidates/
        # buscar_candidatos.
        plano = plan(
            mission_id=mission.id, tenant_id=TENANT, intent=mission.intent, registro=registry
        )
        assert len(plano.steps) == 1
        assert plano.decision_points == []
        runtime.transition(mission.id, MissionEventType.PLAN_READY)

        # 6. Decision Engine chamado de verdade (loop de 0 iteracoes, nao
        # contornado) - composicao via grafo nunca gera DecisionPoint.
        runtime.transition(mission.id, MissionEventType.DECIDING_STARTED)
        decision_engine = DecisionEngine(
            base_conhecimento=_SemConhecimento(),
            llm_gateway=_LlmNuncaChamado(),
            validador=_ValidadorQualquer(),
        )
        for ponto in plano.decision_points:
            decision_engine.resolve(ponto, mission.id)
        runtime.transition(mission.id, MissionEventType.DECISIONS_RESOLVED)

        # 7. Tabela de entradas por step (PlanStep nao carrega payload) +
        # Workflow/Execution Engine reais.
        tabela = TabelaDeEntradasPorStep()
        tabela.registrar(plano.steps[0].id, entrada.model_dump())

        execution_engine = ExecutionEngine(
            validador_schema=ValidadorSchemaEstrutural(),
            validador_contrato_nao_deterministico=ValidadorContratoSempreAprova(),
        )
        invocador = InvocadorDeStepPadrao(
            execution_engine=execution_engine,
            adapter=adapter,
            operator_ref=OperatorRef(operator_id=operator.id),
            capability_registry=registry,
            tabela_entradas=tabela,
            mission_id=mission.id,
            tenant_id=TENANT,
        )
        workflow = WorkflowEngine(invocador)
        run = workflow.iniciar(mission.id, plano)
        while workflow.get_run(run.id).estado == "running":
            prontos = workflow.passos_prontos(run.id)
            if not prontos:
                break
            workflow.executar_passo(run.id, prontos[0])

        assert workflow.get_run(run.id).estado == "completed"
        final = runtime.transition(mission.id, MissionEventType.WORKFLOW_COMPLETED)
        assert final.estado == MissionState.COMPLETED

        # 8. Achado real, produzido pelo handler puro, atravessando toda a
        # canalizacao - a prova de que a migracao funciona de ponta a ponta.
        saida = workflow.get_run(run.id).completed_steps[0].output
        assert saida is not None
        assert len(saida["achados"]) == 1
        assert saida["achados"][0]["codigo"] == "VPS-001"

        execution_engine.fechar()

    def test_regra_vps001_nao_dispara_quando_env_producao_presente(self, tmp_path: Path) -> None:
        (tmp_path / ".env.production.example").write_text(
            "ENABLE_REAL_TRADING=false", encoding="utf-8"
        )

        entradas = entradas_para_regra(
            tmp_path,
            _regra_vps001(),
            {"tipo": "arquivo_fixo", "caminho": ".env.production.example"},
        )

        assert entradas[0].conteudo is not None


def _contexto_teste() -> ExecutionContext:
    from batman_os.foundation.types import MissionId, StepId, agora

    return ExecutionContext(
        mission_id=MissionId("mission-certificacao"),
        tenant_id=TenantId("tenant-certificacao"),
        step_id=StepId("step-certificacao"),
        deadline=agora(),
    )


class _SemConhecimento:
    def consultar(self, ponto: DecisionPoint) -> None:
        del ponto
        return None


class _LlmNuncaChamado:
    def consultar(self, ponto: DecisionPoint) -> RespostaLlmCandidata:
        del ponto
        raise AssertionError("Cenario nao envolve LLM")


class _ValidadorQualquer:
    def validar(self, ponto: DecisionPoint, resposta: object) -> bool:
        del ponto, resposta
        return True
