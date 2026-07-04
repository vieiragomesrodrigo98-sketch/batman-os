"""Testes de Recuperação e Fallback (Vol.V Cap.22) — AT-22.1 a AT-22.3."""

from __future__ import annotations

from datetime import timedelta

import pytest

from batman_os.foundation.types import (
    CapabilityId,
    CapabilityRef,
    Criticidade,
    DegradationRecord,
    EscalationPolicy,
    ImpactoDegradacao,
    MissionId,
    MissionTypeId,
    RecoveryStrategy,
    Reversibilidade,
    StepId,
    TenantId,
    TipoRecoveryStrategy,
)
from batman_os.kernel.event_bus import EventBus
from batman_os.kernel.mission_runtime import (
    DegradacaoSemEvidencia,
    MissionEventType,
    MissionIntent,
    MissionRuntime,
    MissionState,
)
from batman_os.workflow.missions import MissionTypeDefinition, MissionTypeRegistry
from batman_os.workflow.recovery import (
    FallbackChain,
    GapDeFallbackChain,
    deveria_gerar_candidato_de_gap,
    validar_fallback_chains,
)


def _estrategia_fallback(capability_id: str | None) -> RecoveryStrategy:
    return RecoveryStrategy(
        tipo=TipoRecoveryStrategy.FALLBACK_CAPABILITY,
        alternative_capability=(
            CapabilityRef(capability_id=CapabilityId(capability_id), versao="1.0.0")
            if capability_id is not None
            else None
        ),
    )


class TestAT221PartialSuccessNuncaParaStepCritico:
    def test_step_critico_com_partial_success_reprova(self) -> None:
        chain = FallbackChain(
            step_id=StepId("s-1"),
            chain=[_estrategia_fallback("alt")],
            on_chain_exhausted="partial-success",
        )

        with pytest.raises(GapDeFallbackChain):
            validar_fallback_chains(
                [chain],
                steps_criticos={StepId("s-1")},
                schema_compativel=lambda _c, _s: True,
            )

    def test_step_nao_critico_com_partial_success_e_aceito(self) -> None:
        chain = FallbackChain(
            step_id=StepId("s-1"),
            chain=[_estrategia_fallback("alt")],
            on_chain_exhausted="partial-success",
        )

        validar_fallback_chains(
            [chain], steps_criticos=set(), schema_compativel=lambda _c, _s: True
        )  # nao levanta

    def test_step_critico_com_fail_ou_escalate_e_aceito(self) -> None:
        chain_fail = FallbackChain(
            step_id=StepId("s-1"), chain=[_estrategia_fallback("alt")], on_chain_exhausted="fail"
        )
        chain_escalate = FallbackChain(
            step_id=StepId("s-2"),
            chain=[_estrategia_fallback("alt")],
            on_chain_exhausted="escalate",
        )

        validar_fallback_chains(
            [chain_fail, chain_escalate],
            steps_criticos={StepId("s-1"), StepId("s-2")},
            schema_compativel=lambda _c, _s: True,
        )  # nao levanta


class TestAT222FallbackCapabilityExigeSchemaCompativel:
    def test_sem_alternative_capability_declarada_reprova(self) -> None:
        chain = FallbackChain(
            step_id=StepId("s-1"), chain=[_estrategia_fallback(None)], on_chain_exhausted="fail"
        )

        with pytest.raises(GapDeFallbackChain):
            validar_fallback_chains(
                [chain], steps_criticos=set(), schema_compativel=lambda _c, _s: True
            )

    def test_schema_incompativel_reprova(self) -> None:
        chain = FallbackChain(
            step_id=StepId("s-1"),
            chain=[_estrategia_fallback("notify-via-email")],
            on_chain_exhausted="fail",
        )

        with pytest.raises(GapDeFallbackChain):
            validar_fallback_chains(
                [chain], steps_criticos=set(), schema_compativel=lambda _c, _s: False
            )

    def test_schema_compativel_certifica(self) -> None:
        chain = FallbackChain(
            step_id=StepId("s-1"),
            chain=[_estrategia_fallback("notify-via-email")],
            on_chain_exhausted="fail",
        )

        validar_fallback_chains(
            [chain], steps_criticos=set(), schema_compativel=lambda _c, _s: True
        )  # nao levanta

    def test_estrategia_nao_fallback_nao_exige_schema(self) -> None:
        chain = FallbackChain(
            step_id=StepId("s-1"),
            chain=[RecoveryStrategy(tipo=TipoRecoveryStrategy.RETRY, max_tentativas=3)],
            on_chain_exhausted="fail",
        )

        validar_fallback_chains(
            [chain], steps_criticos=set(), schema_compativel=lambda _c, _s: False
        )  # nao levanta - nao ha fallback-capability nesta chain


class TestAT223PartiallyCompletedExigeDegradationRecord:
    def _runtime_com_missao_executando(self) -> tuple[MissionRuntime, MissionId]:
        registro = MissionTypeRegistry()
        registro.register(
            MissionTypeDefinition(
                id=MissionTypeId("investigate-incident"),
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
        runtime = MissionRuntime(EventBus(), tipos=registro)
        mission = runtime.create(
            MissionIntent(dados={}),
            MissionTypeId("investigate-incident"),
            tenant_id=TenantId("t-1"),
        )
        runtime.transition(mission.id, MissionEventType.PLANNING_STARTED)
        runtime.transition(mission.id, MissionEventType.PLAN_READY)
        runtime.transition(mission.id, MissionEventType.DECIDING_STARTED)
        runtime.transition(mission.id, MissionEventType.DECISIONS_RESOLVED)
        return runtime, mission.id

    def test_sem_degradation_record_falha(self) -> None:
        runtime, mission_id = self._runtime_com_missao_executando()

        with pytest.raises(DegradacaoSemEvidencia):
            runtime.transition(mission_id, MissionEventType.WORKFLOW_PARTIALLY_COMPLETED)

    def test_com_degradation_record_transiciona(self) -> None:
        runtime, mission_id = self._runtime_com_missao_executando()

        degradacao = DegradationRecord(
            step_id=StepId("s-1"), exhausted_chain=[], impact=ImpactoDegradacao.COSMETIC
        )
        final = runtime.transition(
            mission_id, MissionEventType.WORKFLOW_PARTIALLY_COMPLETED, degradations=[degradacao]
        )

        assert final.estado == MissionState.PARTIALLY_COMPLETED
        assert final.degradations == [degradacao]

    def test_partially_completed_e_estado_terminal_com_cognitive_debt_flag(self) -> None:
        runtime, mission_id = self._runtime_com_missao_executando()
        degradacao = DegradationRecord(
            step_id=StepId("s-1"), exhausted_chain=[], impact=ImpactoDegradacao.COSMETIC
        )

        final = runtime.transition(
            mission_id, MissionEventType.WORKFLOW_PARTIALLY_COMPLETED, degradations=[degradacao]
        )

        assert final.cognitive_debt_flag is not None


class TestRelacaoComCognitiveDebt:
    def test_requires_follow_up_gera_candidato(self) -> None:
        degradacao = DegradationRecord(
            step_id=StepId("s-1"), exhausted_chain=[], impact=ImpactoDegradacao.REQUIRES_FOLLOW_UP
        )
        assert deveria_gerar_candidato_de_gap(degradacao) is True

    def test_cosmetic_nao_gera_candidato(self) -> None:
        degradacao = DegradationRecord(
            step_id=StepId("s-1"), exhausted_chain=[], impact=ImpactoDegradacao.COSMETIC
        )
        assert deveria_gerar_candidato_de_gap(degradacao) is False

    def test_reduced_functionality_nao_gera_candidato(self) -> None:
        degradacao = DegradationRecord(
            step_id=StepId("s-1"),
            exhausted_chain=[],
            impact=ImpactoDegradacao.REDUCED_FUNCTIONALITY,
        )
        assert deveria_gerar_candidato_de_gap(degradacao) is False
