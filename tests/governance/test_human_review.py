"""Testes de Human Review (Vol.VII Cap.28) — AT-28.1 a AT-28.3."""

from __future__ import annotations

import pytest

from batman_os.foundation.types import Evidence, agora
from batman_os.governance.human_review import (
    HumanReviewDecision,
    HumanReviewRequest,
    PapelDeRevisorNaoAutorizado,
    RationaleObrigatorio,
    ReviewerId,
    ReviewerRole,
    ReviewRequestId,
    StatusRevisao,
    TipoRevisao,
    decidir,
    emitir_referencia,
    papeis_autorizados,
    reabrir_como_nova_solicitacao,
)


def _solicitacao(
    kind: TipoRevisao = TipoRevisao.RULE_PROMOTION,
    required_reviewer_role: ReviewerRole = ReviewerRole.DOMAIN_EXPERT,
) -> HumanReviewRequest:
    return HumanReviewRequest(
        kind=kind,
        subject_ref="rule-candidate-1",
        evidence=[Evidence(origem="teste", evidencias=["x"])],
        required_reviewer_role=required_reviewer_role,
        sla_deadline=agora(),
    )


class TestAT281RationaleObrigatorioMesmoEmAprovacao:
    def test_decision_com_rationale_vazio_falha(self) -> None:
        with pytest.raises(RationaleObrigatorio):
            HumanReviewDecision(
                request_id=ReviewRequestId("req-1"),
                reviewer_id=ReviewerId("rev-1"),
                reviewer_role=ReviewerRole.DOMAIN_EXPERT,
                decision="approved",
                rationale="",
            )

    def test_decision_com_rationale_so_espacos_falha(self) -> None:
        with pytest.raises(RationaleObrigatorio):
            HumanReviewDecision(
                request_id=ReviewRequestId("req-1"),
                reviewer_id=ReviewerId("rev-1"),
                reviewer_role=ReviewerRole.DOMAIN_EXPERT,
                decision="approved",
                rationale="   ",
            )

    def test_rejeicao_tambem_exige_rationale(self) -> None:
        with pytest.raises(RationaleObrigatorio):
            HumanReviewDecision(
                request_id=ReviewRequestId("req-1"),
                reviewer_id=ReviewerId("rev-1"),
                reviewer_role=ReviewerRole.DOMAIN_EXPERT,
                decision="rejected",
                rationale="",
            )

    def test_decision_com_rationale_preenchido_funciona(self) -> None:
        decisao = HumanReviewDecision(
            request_id=ReviewRequestId("req-1"),
            reviewer_id=ReviewerId("rev-1"),
            reviewer_role=ReviewerRole.DOMAIN_EXPERT,
            decision="approved",
            rationale="Padrao consistente em 50 execucoes, shadow mode com 96% de concordancia",
        )
        assert decisao.rationale.startswith("Padrao")


class TestAT282SoDecideQuemTemOPapelExigido:
    def test_papel_diferente_do_exigido_falha(self) -> None:
        solicitacao = _solicitacao(required_reviewer_role=ReviewerRole.SECURITY_REVIEWER)
        decisao = HumanReviewDecision(
            request_id=solicitacao.id,
            reviewer_id=ReviewerId("rev-1"),
            reviewer_role=ReviewerRole.DOMAIN_EXPERT,
            decision="approved",
            rationale="motivo",
        )

        with pytest.raises(PapelDeRevisorNaoAutorizado):
            decidir(solicitacao, decisao)

    def test_papel_correspondente_funciona(self) -> None:
        solicitacao = _solicitacao(required_reviewer_role=ReviewerRole.SECURITY_REVIEWER)
        decisao = HumanReviewDecision(
            request_id=solicitacao.id,
            reviewer_id=ReviewerId("rev-1"),
            reviewer_role=ReviewerRole.SECURITY_REVIEWER,
            decision="approved",
            rationale="motivo",
        )

        resultado = decidir(solicitacao, decisao)
        assert resultado.status == StatusRevisao.APPROVED

    def test_changes_requested_transiciona_status_correto(self) -> None:
        solicitacao = _solicitacao()
        decisao = HumanReviewDecision(
            request_id=solicitacao.id,
            reviewer_id=ReviewerId("rev-1"),
            reviewer_role=ReviewerRole.DOMAIN_EXPERT,
            decision="changes-requested",
            rationale="faltam dados de shadow mode",
        )

        resultado = decidir(solicitacao, decisao)
        assert resultado.status == StatusRevisao.CHANGES_REQUESTED

    def test_tabela_de_autorizacao_secao_283(self) -> None:
        assert papeis_autorizados(TipoRevisao.CAPABILITY_IRREVERSIBLE_APPROVAL) == {
            ReviewerRole.SECURITY_REVIEWER,
            ReviewerRole.GOVERNANCE_LEAD,
        }
        assert papeis_autorizados(TipoRevisao.ADDENDUM_ACCEPTANCE) == {
            ReviewerRole.ARCHITECTURE_REVIEWER,
            ReviewerRole.GOVERNANCE_LEAD,
        }
        # governance-lead pode sobrescrever qualquer papel (secao 28.3)
        for kind in TipoRevisao:
            assert ReviewerRole.GOVERNANCE_LEAD in papeis_autorizados(kind)


class TestAT283DecisaoAprovadaEmiteReferenciaRastreavel:
    def test_decisao_aprovada_emite_referencia(self) -> None:
        decisao = HumanReviewDecision(
            request_id=ReviewRequestId("req-1"),
            reviewer_id=ReviewerId("rev-1"),
            reviewer_role=ReviewerRole.DOMAIN_EXPERT,
            decision="approved",
            rationale="motivo",
        )

        referencia = emitir_referencia(decisao)
        assert "req-1" in referencia
        assert "rev-1" in referencia

    def test_decisao_rejeitada_nunca_emite_referencia(self) -> None:
        decisao = HumanReviewDecision(
            request_id=ReviewRequestId("req-1"),
            reviewer_id=ReviewerId("rev-1"),
            reviewer_role=ReviewerRole.DOMAIN_EXPERT,
            decision="rejected",
            rationale="motivo",
        )

        with pytest.raises(ValueError, match="nao gera HumanReviewRef"):
            emitir_referencia(decisao)

    def test_changes_requested_nunca_emite_referencia(self) -> None:
        decisao = HumanReviewDecision(
            request_id=ReviewRequestId("req-1"),
            reviewer_id=ReviewerId("rev-1"),
            reviewer_role=ReviewerRole.DOMAIN_EXPERT,
            decision="changes-requested",
            rationale="motivo",
        )

        with pytest.raises(ValueError, match="nao gera HumanReviewRef"):
            emitir_referencia(decisao)


class TestReaberturaDeSolicitacaoComChangesRequested:
    def test_reabertura_gera_nova_solicitacao_pending(self) -> None:
        original = _solicitacao()
        nova = reabrir_como_nova_solicitacao(original)

        assert nova.id != original.id
        assert nova.status == StatusRevisao.PENDING
        assert nova.kind == original.kind
        assert nova.subject_ref == original.subject_ref
        assert nova.required_reviewer_role == original.required_reviewer_role

    def test_reabertura_acumula_evidencia_adicional(self) -> None:
        original = _solicitacao()
        nova_evidencia = Evidence(origem="correcao", evidencias=["dados adicionais"])

        nova = reabrir_como_nova_solicitacao(original, evidencia_adicional=[nova_evidencia])

        assert len(nova.evidence) == len(original.evidence) + 1
        assert nova_evidencia in nova.evidence
