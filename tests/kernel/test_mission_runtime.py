"""Testes do Mission Runtime (Vol.II Cap.6) — AT-6.1, AT-6.2, AT-6.4.

AT-6.3 (replay deterministico de planos para o mesmo intent) e responsabilidade
do Planning Engine (Vol.II Cap.7, AT-7.1), nao do Mission Runtime — o Mission
Runtime nao gera planos, apenas os referencia por `plan_id`. Testado la.
"""

from __future__ import annotations

import pytest

from batman_os.foundation.types import MissionTypeId, TenantId
from batman_os.kernel.event_bus import EventBus
from batman_os.kernel.mission_runtime import (
    CognitiveDebtFlag,
    Mission,
    MissionEventType,
    MissionIntent,
    MissionRuntime,
    MissionState,
    TransicaoInvalida,
)


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


@pytest.fixture
def runtime(event_bus: EventBus) -> MissionRuntime:
    return MissionRuntime(event_bus)


def _cria(runtime: MissionRuntime) -> Mission:
    tipo = MissionTypeId("investigate-incident")
    return runtime.create(
        MissionIntent(dados={"exemplo": True}), tipo, tenant_id=TenantId("tenant-1")
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
    runtime = MissionRuntime(EventBus())
    mission = _cria(runtime)

    with pytest.raises(TransicaoInvalida):
        runtime.transition(mission.id, MissionEventType.DECISIONS_RESOLVED)


def test_awaiting_human_e_awaiting_llm_sempre_retornam_a_deciding() -> None:
    """Invariante 2 (secao 6.3.1)."""
    runtime = MissionRuntime(EventBus())
    mission = _cria(runtime)
    runtime.transition(mission.id, MissionEventType.PLANNING_STARTED)
    runtime.transition(mission.id, MissionEventType.PLAN_READY)
    runtime.transition(mission.id, MissionEventType.DECIDING_STARTED)

    aguardando = runtime.transition(mission.id, MissionEventType.ESCALATED_TO_HUMAN)
    assert aguardando.estado == MissionState.AWAITING_HUMAN

    de_volta = runtime.transition(mission.id, MissionEventType.ESCALATION_RESOLVED)
    assert de_volta.estado == MissionState.DECIDING
