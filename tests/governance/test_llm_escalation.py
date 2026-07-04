"""Testes de LLM Escalation (Vol.VII Cap.29) — AT-29.1 a AT-29.3."""

from __future__ import annotations

from datetime import timedelta

import pytest

from batman_os.foundation.types import (
    DateRange,
    DecisionOption,
    DecisionPointId,
    Evidence,
    HumanReviewRef,
    MissionId,
    Timestamp,
    agora,
)
from batman_os.governance.llm_escalation import (
    LLMEscalationPolicy,
    PolicyId,
    PoliticaSemAprovacao,
    RatePolicy,
    RelaxamentoDeControleSemEvidencia,
    RequerAprovacaoHumana,
    ativar_politica,
    calcular_llm_usage_audit,
    relaxa_controle,
    validar_mudanca_de_politica,
)
from batman_os.kernel.decision_engine import Decision, ResolvedBy

_APPROVED_BY_PADRAO = HumanReviewRef("review-1")


def _politica(
    requires_human_co_approval: RequerAprovacaoHumana = "always",
    approved_by: HumanReviewRef | None = _APPROVED_BY_PADRAO,
    version: str = "1.0.0",
) -> LLMEscalationPolicy:
    return LLMEscalationPolicy(
        id=PolicyId("pol-1"),
        version=version,
        scope="global",
        max_retries_per_decision_point=3,
        circuit_breaker_threshold=RatePolicy(taxa_maxima=0.3, tamanho_janela=20),
        requires_human_co_approval=requires_human_co_approval,
        output_validation_level="schema-only",
        approved_by=approved_by,
    )


class TestAT291PoliticaExigeAprovacaoParaActive:
    def test_sem_approved_by_falha(self) -> None:
        politica = _politica(approved_by=None)
        with pytest.raises(PoliticaSemAprovacao):
            ativar_politica(politica)

    def test_com_approved_by_ativa(self) -> None:
        politica = _politica()
        ativada = ativar_politica(politica)
        assert ativada.status == "active"


class TestAT292RelaxamentoDeControleExigeEvidencia:
    def test_ordem_de_restritividade(self) -> None:
        assert relaxa_controle("always", "irreversible-only") is True
        assert relaxa_controle("always", "never") is True
        assert relaxa_controle("irreversible-only", "never") is True
        assert relaxa_controle("never", "always") is False
        assert relaxa_controle("always", "always") is False

    def test_relaxamento_sem_rationale_falha(self) -> None:
        anterior = _politica(requires_human_co_approval="always")
        nova = _politica(requires_human_co_approval="irreversible-only", version="2.0.0")

        with pytest.raises(RelaxamentoDeControleSemEvidencia):
            validar_mudanca_de_politica(
                anterior,
                nova,
                rationale="",
                evidencia_quantitativa={"resolvedByLLMPercentage": 0.1},
            )

    def test_relaxamento_sem_evidencia_quantitativa_falha(self) -> None:
        anterior = _politica(requires_human_co_approval="always")
        nova = _politica(requires_human_co_approval="irreversible-only", version="2.0.0")

        with pytest.raises(RelaxamentoDeControleSemEvidencia):
            validar_mudanca_de_politica(
                anterior, nova, rationale="parece seguro", evidencia_quantitativa=None
            )

    def test_relaxamento_com_rationale_e_evidencia_passa(self) -> None:
        anterior = _politica(requires_human_co_approval="always")
        nova = _politica(requires_human_co_approval="irreversible-only", version="2.0.0")

        validar_mudanca_de_politica(
            anterior,
            nova,
            rationale="6 meses de dados mostram 0.1% de falha de validacao",
            evidencia_quantitativa={"resolvedByLLMPercentage": 0.1, "rejectedByValidation": 0.001},
        )  # nao levanta

    def test_aperto_de_controle_nao_exige_evidencia(self) -> None:
        anterior = _politica(requires_human_co_approval="never")
        nova = _politica(requires_human_co_approval="always", version="2.0.0")

        validar_mudanca_de_politica(
            anterior, nova, rationale="", evidencia_quantitativa=None
        )  # nao levanta - apertar controle nao exige evidencia extra

    def test_manter_o_mesmo_nivel_nao_exige_evidencia(self) -> None:
        anterior = _politica(requires_human_co_approval="always")
        nova = _politica(requires_human_co_approval="always", version="1.0.1")

        validar_mudanca_de_politica(anterior, nova, rationale="", evidencia_quantitativa=None)


class TestAT293AuditoriaReconciliavel:
    def _decisao(self, resolved_by: ResolvedBy, resolved_at: Timestamp) -> Decision:
        return Decision(
            decision_point_id=DecisionPointId("dp-1"),
            mission_id=MissionId("m-1"),
            resolved_by=resolved_by,
            chosen_option=DecisionOption(id="a", descricao="A"),
            confidence=0.9,
            evidence=[Evidence(origem="teste", evidencias=["x"])],
            resolved_at=resolved_at,
        )

    def test_mesma_lista_produz_sempre_o_mesmo_relatorio(self) -> None:
        agora_ = agora()
        periodo = DateRange(inicio=agora_ - timedelta(days=1), fim=agora_ + timedelta(days=1))
        decisions = [
            self._decisao("llm", agora_),
            self._decisao("knowledge", agora_),
            self._decisao("llm", agora_),
            self._decisao("human", agora_),
        ]

        auditoria_1 = calcular_llm_usage_audit(decisions, periodo)
        auditoria_2 = calcular_llm_usage_audit(decisions, periodo)

        assert auditoria_1 == auditoria_2
        assert auditoria_1.total_decision_points == 4
        assert auditoria_1.resolved_by_llm == 2
        assert auditoria_1.resolved_by_llm_percentage == 0.5

    def test_decisoes_fora_do_periodo_sao_excluidas(self) -> None:
        agora_ = agora()
        periodo = DateRange(inicio=agora_, fim=agora_ + timedelta(days=1))
        dentro = self._decisao("llm", agora_ + timedelta(hours=1))
        fora = self._decisao("llm", agora_ - timedelta(days=5))

        auditoria = calcular_llm_usage_audit([dentro, fora], periodo)

        assert auditoria.total_decision_points == 1
        assert auditoria.resolved_by_llm == 1

    def test_percentual_zero_sem_decisoes_no_periodo(self) -> None:
        agora_ = agora()
        periodo = DateRange(inicio=agora_, fim=agora_ + timedelta(days=1))
        auditoria = calcular_llm_usage_audit([], periodo)

        assert auditoria.resolved_by_llm_percentage == 0.0
