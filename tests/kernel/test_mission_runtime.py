"""Testes do Mission Runtime (Vol.II Cap.6) — AT-6.1, AT-6.2, AT-6.4.

AT-6.3 (replay deterministico de planos para o mesmo intent) e responsabilidade
do Planning Engine (Vol.II Cap.7, AT-7.1), nao do Mission Runtime — o Mission
Runtime nao gera planos, apenas os referencia por `plan_id`. Testado la.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from batman_os.foundation.types import (
    CognitiveDebtFlag,
    Criticidade,
    DegradationRecord,
    EscalationPolicy,
    ImpactoDegradacao,
    MissionId,
    MissionTypeId,
    Reversibilidade,
    StepId,
    TenantId,
)
from batman_os.kernel.event_bus import EventBus
from batman_os.kernel.mission_runtime import (
    Mission,
    MissionEventType,
    MissionIntent,
    MissionRuntime,
    MissionState,
    TransicaoInvalida,
)
from batman_os.workflow.missions import MissionTypeDefinition, MissionTypeRegistry

TIPO_INVESTIGAR_INCIDENTE = MissionTypeId("investigate-incident")


def _registro_tipos() -> MissionTypeRegistry:
    registro = MissionTypeRegistry()
    registro.register(
        MissionTypeDefinition(
            id=TIPO_INVESTIGAR_INCIDENTE,
            criticality=Criticidade.MEDIUM,
            default_sla=timedelta(hours=1),
            escalation_defaults=EscalationPolicy(
                confidence_threshold=0.7,
                preferred_escalation="human",
                max_llm_retries=1,
                reversibility=Reversibilidade.REVERSIVEL,
            ),
        )
    )
    return registro


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


@pytest.fixture
def runtime(event_bus: EventBus) -> MissionRuntime:
    return MissionRuntime(event_bus, tipos=_registro_tipos())


def _cria(runtime: MissionRuntime) -> Mission:
    return runtime.create(
        MissionIntent(dados={"exemplo": True}),
        TIPO_INVESTIGAR_INCIDENTE,
        tenant_id=TenantId("tenant-1"),
    )


def _ate_executando(runtime: MissionRuntime, mission: Mission) -> Mission:
    runtime.transition(mission.id, MissionEventType.PLANNING_STARTED)
    runtime.transition(mission.id, MissionEventType.PLAN_READY)
    runtime.transition(mission.id, MissionEventType.DECIDING_STARTED)
    return runtime.transition(mission.id, MissionEventType.DECISIONS_RESOLVED)


class TestAT61CognitiveDebtFlag:
    def test_missao_totalmente_autonoma_flag_autonomous(self, runtime: MissionRuntime) -> None:
        mission = _cria(runtime)
        _ate_executando(runtime, mission)
        final = runtime.transition(mission.id, MissionEventType.WORKFLOW_COMPLETED)

        assert final.estado == MissionState.COMPLETED
        assert final.cognitive_debt_flag == CognitiveDebtFlag.AUTONOMOUS

    def test_missao_escalada_a_humano_flag_human(self, runtime: MissionRuntime) -> None:
        mission = _cria(runtime)
        runtime.transition(mission.id, MissionEventType.PLANNING_STARTED)
        runtime.transition(mission.id, MissionEventType.PLAN_READY)
        runtime.transition(mission.id, MissionEventType.DECIDING_STARTED)
        runtime.transition(mission.id, MissionEventType.ESCALATED_TO_HUMAN)
        runtime.transition(mission.id, MissionEventType.ESCALATION_RESOLVED)
        runtime.transition(mission.id, MissionEventType.DECISIONS_RESOLVED)
        final = runtime.transition(mission.id, MissionEventType.WORKFLOW_COMPLETED)

        assert final.cognitive_debt_flag == CognitiveDebtFlag.HUMAN

    def test_missao_escalada_a_llm_flag_llm(self, runtime: MissionRuntime) -> None:
        mission = _cria(runtime)
        runtime.transition(mission.id, MissionEventType.PLANNING_STARTED)
        runtime.transition(mission.id, MissionEventType.PLAN_READY)
        runtime.transition(mission.id, MissionEventType.DECIDING_STARTED)
        runtime.transition(mission.id, MissionEventType.ESCALATED_TO_LLM)
        runtime.transition(mission.id, MissionEventType.ESCALATION_RESOLVED)
        runtime.transition(mission.id, MissionEventType.DECISIONS_RESOLVED)
        final = runtime.transition(mission.id, MissionEventType.WORKFLOW_COMPLETED)

        assert final.cognitive_debt_flag == CognitiveDebtFlag.LLM

    def test_empate_humano_e_llm_desempata_para_human(self, runtime: MissionRuntime) -> None:
        mission = _cria(runtime)
        runtime.transition(mission.id, MissionEventType.PLANNING_STARTED)
        runtime.transition(mission.id, MissionEventType.PLAN_READY)
        runtime.transition(mission.id, MissionEventType.DECIDING_STARTED)
        runtime.transition(mission.id, MissionEventType.ESCALATED_TO_LLM)
        runtime.transition(mission.id, MissionEventType.ESCALATION_RESOLVED)
        runtime.transition(mission.id, MissionEventType.ESCALATED_TO_HUMAN)
        runtime.transition(mission.id, MissionEventType.ESCALATION_RESOLVED)
        runtime.transition(mission.id, MissionEventType.DECISIONS_RESOLVED)
        final = runtime.transition(mission.id, MissionEventType.WORKFLOW_COMPLETED)

        assert final.cognitive_debt_flag == CognitiveDebtFlag.HUMAN

    def test_flag_tambem_definido_em_cancelled(self, runtime: MissionRuntime) -> None:
        mission = _cria(runtime)
        final = runtime.transition(mission.id, MissionEventType.CANCELLATION_REQUESTED)

        assert final.estado == MissionState.CANCELLED
        assert final.cognitive_debt_flag == CognitiveDebtFlag.AUTONOMOUS

    def test_flag_so_e_atribuido_em_estado_terminal(self, runtime: MissionRuntime) -> None:
        mission = _cria(runtime)
        em_planning = runtime.transition(mission.id, MissionEventType.PLANNING_STARTED)

        assert em_planning.cognitive_debt_flag is None


class TestAT62ReconciliacaoComEventBus:
    def test_toda_transicao_tem_evento_correspondente_publicado(
        self, runtime: MissionRuntime, event_bus: EventBus
    ) -> None:
        mission = _cria(runtime)
        _ate_executando(runtime, mission)
        final = runtime.transition(mission.id, MissionEventType.WORKFLOW_COMPLETED)

        historia = event_bus.replay(mission.id)
        ultimo_evento = historia[-1]

        assert ultimo_evento.tipo == f"Mission{final.estado.value}"
        assert ultimo_evento.payload["estado"] == final.estado.value

    def test_transicao_invalida_nao_publica_evento_nem_muda_estado(
        self, runtime: MissionRuntime, event_bus: EventBus
    ) -> None:
        mission = _cria(runtime)
        antes = len(event_bus.replay(mission.id))

        with pytest.raises(TransicaoInvalida):
            runtime.transition(mission.id, MissionEventType.WORKFLOW_COMPLETED)

        assert len(event_bus.replay(mission.id)) == antes
        assert runtime.get_state(mission.id) == MissionState.CREATED


class TestAT64CancelamentoEmTempoFinito:
    @pytest.mark.parametrize(
        "chegar_em",
        [
            [],
            [MissionEventType.PLANNING_STARTED],
            [
                MissionEventType.PLANNING_STARTED,
                MissionEventType.PLAN_READY,
                MissionEventType.DECIDING_STARTED,
            ],
        ],
    )
    def test_cancelamento_a_partir_de_estados_nao_terminais_definidos_no_diagrama(
        self, runtime: MissionRuntime, chegar_em: list[MissionEventType]
    ) -> None:
        mission = _cria(runtime)
        for evento in chegar_em:
            runtime.transition(mission.id, evento)

        final = runtime.transition(mission.id, MissionEventType.CANCELLATION_REQUESTED)

        assert final.estado == MissionState.CANCELLED

    def test_cancelamento_a_partir_de_executing(self, runtime: MissionRuntime) -> None:
        mission = _cria(runtime)
        _ate_executando(runtime, mission)

        final = runtime.transition(mission.id, MissionEventType.CANCELLATION_REQUESTED)

        assert final.estado == MissionState.CANCELLED


def test_transicao_nunca_pula_estados() -> None:
    """Invariante 1 (secao 6.3.1): Created nao pode ir direto para Executing."""
    runtime = MissionRuntime(EventBus(), tipos=_registro_tipos())
    mission = _cria(runtime)

    with pytest.raises(TransicaoInvalida):
        runtime.transition(mission.id, MissionEventType.DECISIONS_RESOLVED)


class TestFase2Estagio21PersistenciaHibrida:
    """Fase 2 do roadmap de plataforma (`.claude/plans/peaceful-wondering-
    hearth.md`), Estagio 2.1 — cache em memoria inalterado no caminho
    quente; hidratacao via replay do Event Bus so em cache-miss (segunda
    instancia de `MissionRuntime` compartilhando o mesmo `EventBus`,
    simulando processo reiniciado)."""

    def test_cache_miss_reconstroi_mission_via_replay(self, event_bus: EventBus) -> None:
        runtime_a = MissionRuntime(event_bus, tipos=_registro_tipos())
        mission = _cria(runtime_a)
        _ate_executando(runtime_a, mission)
        final = runtime_a.transition(mission.id, MissionEventType.WORKFLOW_COMPLETED)

        runtime_b = MissionRuntime(event_bus, tipos=_registro_tipos())
        hidratada = runtime_b.get_mission(mission.id)

        assert hidratada.estado == final.estado
        assert hidratada.tenant_id == final.tenant_id
        assert hidratada.tipo == final.tipo
        assert hidratada.intent.dados == final.intent.dados
        assert hidratada.cognitive_debt_flag == final.cognitive_debt_flag

    def test_cache_miss_reconstroi_degradations(self, event_bus: EventBus) -> None:
        runtime_a = MissionRuntime(event_bus, tipos=_registro_tipos())
        mission = _cria(runtime_a)
        _ate_executando(runtime_a, mission)
        degradacao = DegradationRecord(
            step_id=StepId("passo-1"),
            exhausted_chain=[],
            impact=ImpactoDegradacao.REDUCED_FUNCTIONALITY,
        )
        runtime_a.transition(
            mission.id,
            MissionEventType.WORKFLOW_PARTIALLY_COMPLETED,
            degradations=[degradacao],
        )

        runtime_b = MissionRuntime(event_bus, tipos=_registro_tipos())
        hidratada = runtime_b.get_mission(mission.id)

        assert len(hidratada.degradations) == 1
        assert hidratada.degradations[0].step_id == degradacao.step_id

    def test_mission_id_desconhecido_ainda_levanta_keyerror(self, event_bus: EventBus) -> None:
        runtime = MissionRuntime(event_bus, tipos=_registro_tipos())

        with pytest.raises(KeyError):
            runtime.get_mission(MissionId("inexistente"))

    def test_hidratacao_nao_e_chamada_no_caminho_quente(
        self, runtime: MissionRuntime, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mission = _cria(runtime)

        def _falhar(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("_hidratar_de nao deveria rodar com Mission em cache")

        monkeypatch.setattr(runtime, "_hidratar_de", _falhar)

        assert runtime.get_mission(mission.id).id == mission.id


def test_awaiting_human_e_awaiting_llm_sempre_retornam_a_deciding() -> None:
    """Invariante 2 (secao 6.3.1)."""
    runtime = MissionRuntime(EventBus(), tipos=_registro_tipos())
    mission = _cria(runtime)
    runtime.transition(mission.id, MissionEventType.PLANNING_STARTED)
    runtime.transition(mission.id, MissionEventType.PLAN_READY)
    runtime.transition(mission.id, MissionEventType.DECIDING_STARTED)

    aguardando = runtime.transition(mission.id, MissionEventType.ESCALATED_TO_HUMAN)
    assert aguardando.estado == MissionState.AWAITING_HUMAN

    de_volta = runtime.transition(mission.id, MissionEventType.ESCALATION_RESOLVED)
    assert de_volta.estado == MissionState.DECIDING
