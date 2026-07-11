"""Testes de `orchestration/mission_resumption.py` (Fase 2 do roadmap de
plataforma, `.claude/plans/peaceful-wondering-hearth.md`, Estagio 2.5) —
watchdog de SLA + retomada real de Missoes em `AwaitingHuman` apos um
restart de processo, sem replanejar e sem reexecutar passos ja concluidos.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from batman_os.foundation.types import (
    CapabilityId,
    CapabilityRef,
    Criticidade,
    DecisionOption,
    EscalationPolicy,
    Evidence,
    MissionId,
    MissionTypeId,
    Reversibilidade,
    TenantId,
)
from batman_os.governance.governance_engine import (
    FonteAlerta,
    GovernanceEngine,
)
from batman_os.governance.human_review import HumanReviewRequest, ReviewerRole, TipoRevisao
from batman_os.kernel.decision_engine import DecisionEngine
from batman_os.kernel.event_bus import EventBus
from batman_os.kernel.mission_runtime import (
    MissionEventType,
    MissionIntent,
    MissionRuntime,
    MissionState,
)
from batman_os.kernel.planning_engine import DecisionPoint, plan
from batman_os.kernel.workflow_engine import ResultadoInvocacao, WorkflowEngine
from batman_os.orchestration.mission_resumption import (
    MissaoNaoRetomavel,
    RespostaHumanaChegada,
    executar_ciclo_watchdog,
    retomar_missao,
)
from batman_os.workflow.missions import MissionTypeDefinition, MissionTypeRegistry

TIPO = MissionTypeId("investigate-incident")
TENANT = TenantId("t-1")
OPCAO = DecisionOption(id="opcao-a", descricao="Fazer A")


def _registro_tipos() -> MissionTypeRegistry:
    registro = MissionTypeRegistry()
    registro.register(
        MissionTypeDefinition(
            id=TIPO,
            criticality=Criticidade.MEDIUM,
            default_sla=timedelta(hours=1),
            escalation_defaults=_politica(),
        )
    )
    return registro


def _politica() -> EscalationPolicy:
    return EscalationPolicy(
        confidence_threshold=0.8,
        preferred_escalation="human",
        max_llm_retries=1,
        reversibility=Reversibilidade.REVERSIVEL,
    )


def _ponto() -> DecisionPoint:
    return DecisionPoint(pergunta="qual acao tomar?", opcoes=[OPCAO], escalation_policy=_politica())


def _ref(nome: str) -> CapabilityRef:
    return CapabilityRef(capability_id=CapabilityId(nome), versao="1.0.0")


class _RegistroCapacidadesFake:
    def buscar_candidatos(self, intent: object) -> list[CapabilityRef]:
        del intent
        return [_ref("passo-1"), _ref("passo-2")]

    def versao(self) -> str:
        return "v1"


class _SemConhecimento:
    def consultar(self, ponto: DecisionPoint) -> None:
        del ponto
        return None


class _LlmNuncaChamado:
    def consultar(self, ponto: DecisionPoint) -> None:
        del ponto
        raise AssertionError("cenario de retomada nao deveria envolver LLM")


class _ValidadorQualquer:
    def validar(self, ponto: DecisionPoint, resposta: object) -> bool:
        del ponto, resposta
        return True


class _InvocadorContavel:
    """Conta chamadas por Capability — prova que um passo ja concluido
    ANTES do "restart" nunca e reinvocado depois da retomada."""

    def __init__(self) -> None:
        self.chamadas: dict[str, int] = {}

    def invocar(self, step: object) -> ResultadoInvocacao:
        chave = str(step.capability.capability_id)  # type: ignore[attr-defined]
        self.chamadas[chave] = self.chamadas.get(chave, 0) + 1
        return ResultadoInvocacao(sucesso=True, output={"ok": True})


def _decision_engine() -> DecisionEngine:
    return DecisionEngine(
        base_conhecimento=_SemConhecimento(),
        llm_gateway=_LlmNuncaChamado(),
        validador=_ValidadorQualquer(),
    )


class TestRetomarMissao:
    def test_resume_apos_restart_sem_reexecutar_passo_ja_concluido(self) -> None:
        event_bus = EventBus()
        invocador = _InvocadorContavel()

        # --- ANTES DO "RESTART" ---
        runtime_antes = MissionRuntime(event_bus, tipos=_registro_tipos())
        mission = runtime_antes.create(
            MissionIntent(dados={"sintoma": "x"}), TIPO, tenant_id=TENANT
        )
        runtime_antes.transition(mission.id, MissionEventType.PLANNING_STARTED)

        plano = plan(
            mission_id=mission.id,
            tenant_id=TENANT,
            intent=mission.intent,
            registro=_RegistroCapacidadesFake(),
            event_bus=event_bus,
        )
        assert len(plano.steps) == 2
        runtime_antes.transition(mission.id, MissionEventType.PLAN_READY)

        runtime_antes.transition(mission.id, MissionEventType.DECIDING_STARTED)
        ponto = _ponto()
        resultado = _decision_engine().resolve(ponto, mission.id)
        assert resultado.escalonado_para == "human"
        runtime_antes.transition(mission.id, MissionEventType.ESCALATED_TO_HUMAN)
        assert runtime_antes.get_state(mission.id) == MissionState.AWAITING_HUMAN

        workflow_antes = WorkflowEngine(invocador, event_bus=event_bus)
        run = workflow_antes.iniciar(mission.id, plano)
        workflow_antes.executar_passo(run.id, plano.steps[0])
        assert len(workflow_antes.get_run(run.id).completed_steps) == 1
        assert invocador.chamadas == {"passo-1": 1}

        # --- "RESTART": instancias novas, MESMO EventBus ---
        runtime_depois = MissionRuntime(event_bus, tipos=_registro_tipos())
        workflow_depois = WorkflowEngine(invocador, event_bus=event_bus)
        decision_engine_depois = _decision_engine()

        resposta = RespostaHumanaChegada(
            mission_id=mission.id,
            workflow_run_id=run.id,
            ponto=ponto,
            opcao_escolhida=OPCAO,
            evidencia=[Evidence(origem="humano", evidencias=["confirmado apos revisao"])],
        )
        retomar_missao(resposta, event_bus, runtime_depois, workflow_depois, decision_engine_depois)

        final_run = workflow_depois.get_run(run.id)
        assert final_run.estado == "completed"
        assert len(final_run.completed_steps) == 2
        # passo-1 nunca foi reinvocado; so passo-2 rodou apos a retomada.
        assert invocador.chamadas == {"passo-1": 1, "passo-2": 1}

        final_mission = runtime_depois.get_mission(mission.id)
        assert final_mission.estado == MissionState.COMPLETED

    def test_missao_que_nao_esta_em_awaiting_human_nao_e_retomavel(self) -> None:
        event_bus = EventBus()
        runtime = MissionRuntime(event_bus, tipos=_registro_tipos())
        mission = runtime.create(MissionIntent(dados={}), TIPO, tenant_id=TENANT)
        # ainda em Created -- nunca chegou a AwaitingHuman

        workflow = WorkflowEngine(_InvocadorContavel(), event_bus=event_bus)
        resposta = RespostaHumanaChegada(
            mission_id=mission.id,
            workflow_run_id="run-inexistente",  # type: ignore[arg-type]
            ponto=_ponto(),
            opcao_escolhida=OPCAO,
            evidencia=[Evidence(origem="humano", evidencias=["x"])],
        )

        with pytest.raises(MissaoNaoRetomavel):
            retomar_missao(resposta, event_bus, runtime, workflow, _decision_engine())

    def test_missao_sem_plano_persistido_nao_e_retomavel(self) -> None:
        event_bus = EventBus()
        runtime = MissionRuntime(event_bus, tipos=_registro_tipos())
        mission = runtime.create(MissionIntent(dados={}), TIPO, tenant_id=TENANT)
        runtime.transition(mission.id, MissionEventType.PLANNING_STARTED)

        plano = plan(
            mission_id=mission.id,
            tenant_id=TENANT,
            intent=mission.intent,
            registro=_RegistroCapacidadesFake(),
            # SEM event_bus -- plano nunca e persistido (Estagio 2.2)
        )
        runtime.transition(mission.id, MissionEventType.PLAN_READY)
        runtime.transition(mission.id, MissionEventType.DECIDING_STARTED)
        _decision_engine().resolve(_ponto(), mission.id)
        runtime.transition(mission.id, MissionEventType.ESCALATED_TO_HUMAN)

        workflow = WorkflowEngine(_InvocadorContavel(), event_bus=event_bus)
        workflow.iniciar(mission.id, plano)

        resposta = RespostaHumanaChegada(
            mission_id=mission.id,
            workflow_run_id="run-qualquer",  # type: ignore[arg-type]
            ponto=_ponto(),
            opcao_escolhida=OPCAO,
            evidencia=[Evidence(origem="humano", evidencias=["x"])],
        )

        with pytest.raises(MissaoNaoRetomavel):
            retomar_missao(resposta, event_bus, runtime, workflow, _decision_engine())


class TestExecutarCicloWatchdog:
    def test_alarma_sla_vencido_e_retoma_missao_em_paralelo_com_isolamento_de_falha(
        self,
    ) -> None:
        event_bus = EventBus()
        runtime = MissionRuntime(event_bus, tipos=_registro_tipos())
        mission_ok = runtime.create(MissionIntent(dados={}), TIPO, tenant_id=TENANT)
        runtime.transition(mission_ok.id, MissionEventType.PLANNING_STARTED)
        plano = plan(
            mission_id=mission_ok.id,
            tenant_id=TENANT,
            intent=mission_ok.intent,
            registro=_RegistroCapacidadesFake(),
            event_bus=event_bus,
        )
        runtime.transition(mission_ok.id, MissionEventType.PLAN_READY)
        runtime.transition(mission_ok.id, MissionEventType.DECIDING_STARTED)
        ponto = _ponto()
        _decision_engine().resolve(ponto, mission_ok.id)
        runtime.transition(mission_ok.id, MissionEventType.ESCALATED_TO_HUMAN)

        workflow = WorkflowEngine(_InvocadorContavel(), event_bus=event_bus)
        run_ok = workflow.iniciar(mission_ok.id, plano)

        solicitacao_vencida = HumanReviewRequest(
            kind=TipoRevisao.RULE_PROMOTION,
            subject_ref="regra-x",
            evidence=[Evidence(origem="sistema", evidencias=["candidato"])],
            required_reviewer_role=ReviewerRole.DOMAIN_EXPERT,
            sla_deadline=plano.gerado_em - timedelta(hours=1),  # ja no passado
        )
        governance = GovernanceEngine()

        resposta_ok = RespostaHumanaChegada(
            mission_id=mission_ok.id,
            workflow_run_id=run_ok.id,
            ponto=ponto,
            opcao_escolhida=OPCAO,
            evidencia=[Evidence(origem="humano", evidencias=["ok"])],
        )
        resposta_invalida = RespostaHumanaChegada(
            mission_id=MissionId("missao-inexistente"),  # type: ignore[arg-type]
            workflow_run_id=run_ok.id,
            ponto=ponto,
            opcao_escolhida=OPCAO,
            evidencia=[Evidence(origem="humano", evidencias=["x"])],
        )

        resultado = executar_ciclo_watchdog(
            [solicitacao_vencida],
            governance,
            [resposta_invalida, resposta_ok],
            event_bus,
            runtime,
            workflow,
            _decision_engine(),
        )

        assert len(resultado.alertas_sla) == 1
        assert resultado.alertas_sla[0].source == FonteAlerta.HUMAN_REVIEW_BACKLOG
        assert resultado.missoes_retomadas == [mission_ok.id]
        assert "missao-inexistente" in resultado.missoes_com_falha_ao_retomar
        assert workflow.get_run(run_ok.id).estado == "completed"
