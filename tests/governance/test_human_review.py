"""Testes de Human Review (Vol.VII Cap.28) — AT-28.1 a AT-28.3."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from batman_os.foundation.types import Evidence, TenantId, Timestamp, agora
from batman_os.governance.governance_engine import FonteAlerta, GovernanceEngine
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
    solicitacoes_do_tenant,
    verificar_sla_e_alarmar,
)

TENANT = TenantId("tenant-1")
OUTRO_TENANT = TenantId("tenant-2")


def _solicitacao(
    kind: TipoRevisao = TipoRevisao.RULE_PROMOTION,
    required_reviewer_role: ReviewerRole = ReviewerRole.DOMAIN_EXPERT,
    sla_deadline: Timestamp | None = None,
    status: StatusRevisao = StatusRevisao.PENDING,
    tenant_id: TenantId = TENANT,
) -> HumanReviewRequest:
    return HumanReviewRequest(
        tenant_id=tenant_id,
        kind=kind,
        subject_ref="rule-candidate-1",
        evidence=[Evidence(origem="teste", evidencias=["x"])],
        required_reviewer_role=required_reviewer_role,
        sla_deadline=sla_deadline or agora(),
        status=status,
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


class TestMilestone4FilaComAlarmeDeSlaReal:
    """Achado de revisão fechado na Milestone 4: `sla_deadline` existia
    desde o Cap.28 mas nada disparava `GovernanceEngine.raise_alert()`
    quando ultrapassado sem decisão."""

    _MOMENTO = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)

    def test_solicitacao_pending_com_prazo_ultrapassado_dispara_alerta(self) -> None:
        solicitacao = _solicitacao(
            sla_deadline=self._MOMENTO - timedelta(hours=1), status=StatusRevisao.PENDING
        )
        governance = GovernanceEngine()

        disparados = verificar_sla_e_alarmar([solicitacao], governance, agora_=self._MOMENTO)

        assert len(disparados) == 1
        assert disparados[0].source == FonteAlerta.HUMAN_REVIEW_BACKLOG
        assert governance.get_open_alerts(source=FonteAlerta.HUMAN_REVIEW_BACKLOG)

    def test_solicitacao_in_review_com_prazo_ultrapassado_tambem_dispara(self) -> None:
        solicitacao = _solicitacao(
            sla_deadline=self._MOMENTO - timedelta(hours=1), status=StatusRevisao.IN_REVIEW
        )
        governance = GovernanceEngine()

        disparados = verificar_sla_e_alarmar([solicitacao], governance, agora_=self._MOMENTO)

        assert len(disparados) == 1

    def test_solicitacao_dentro_do_prazo_nao_dispara(self) -> None:
        solicitacao = _solicitacao(
            sla_deadline=self._MOMENTO + timedelta(hours=1), status=StatusRevisao.PENDING
        )
        governance = GovernanceEngine()

        disparados = verificar_sla_e_alarmar([solicitacao], governance, agora_=self._MOMENTO)

        assert disparados == []
        assert governance.get_open_alerts(source=FonteAlerta.HUMAN_REVIEW_BACKLOG) == []

    def test_solicitacao_ja_decidida_nunca_dispara_mesmo_com_prazo_ultrapassado(self) -> None:
        solicitacao = _solicitacao(
            sla_deadline=self._MOMENTO - timedelta(hours=1), status=StatusRevisao.APPROVED
        )
        governance = GovernanceEngine()

        disparados = verificar_sla_e_alarmar([solicitacao], governance, agora_=self._MOMENTO)

        assert disparados == []

    def test_verifica_varias_solicitacoes_de_uma_vez(self) -> None:
        vencida = _solicitacao(sla_deadline=self._MOMENTO - timedelta(hours=1))
        no_prazo = _solicitacao(sla_deadline=self._MOMENTO + timedelta(hours=1))
        decidida = _solicitacao(
            sla_deadline=self._MOMENTO - timedelta(hours=1), status=StatusRevisao.REJECTED
        )
        governance = GovernanceEngine()

        disparados = verificar_sla_e_alarmar(
            [vencida, no_prazo, decidida], governance, agora_=self._MOMENTO
        )

        assert len(disparados) == 1
        assert disparados[0].evidence[0].origem == f"HumanReviewRequest:{vencida.id}"


class TestFase5Estagio52TenantIdEmHumanReviewRequest:
    """Fase 5 do roadmap de plataforma (isolamento multi-tenant,
    `.claude/plans/peaceful-wondering-hearth.md`), Estagio 5.2."""

    def test_sem_tenant_id_e_rejeitado_pelo_schema(self) -> None:
        with pytest.raises(ValidationError):
            HumanReviewRequest(  # type: ignore[call-arg]
                kind=TipoRevisao.RULE_PROMOTION,
                subject_ref="rule-candidate-1",
                evidence=[Evidence(origem="teste", evidencias=["x"])],
                required_reviewer_role=ReviewerRole.DOMAIN_EXPERT,
                sla_deadline=agora(),
            )

    def test_solicitacoes_do_tenant_filtra_corretamente(self) -> None:
        do_tenant_1 = _solicitacao(tenant_id=TENANT)
        do_tenant_2 = _solicitacao(tenant_id=OUTRO_TENANT)

        filtradas = solicitacoes_do_tenant([do_tenant_1, do_tenant_2], TENANT)

        assert filtradas == [do_tenant_1]

    def test_reabertura_preserva_o_tenant_id_original(self) -> None:
        original = _solicitacao(tenant_id=OUTRO_TENANT, status=StatusRevisao.CHANGES_REQUESTED)

        reaberta = reabrir_como_nova_solicitacao(original)

        assert reaberta.tenant_id == OUTRO_TENANT

    def test_verificar_sla_e_alarmar_permanece_cross_tenant(self) -> None:
        """Deliberado (ver docstring de `verificar_sla_e_alarmar`) — um
        sweep de governanca ve o backlog de todos os tenants, diferente
        de `MissionRuntime.get_mission()` (Estagio 5.1)."""
        momento = datetime(2026, 1, 1, tzinfo=UTC)
        vencida_tenant_1 = _solicitacao(tenant_id=TENANT, sla_deadline=momento - timedelta(hours=1))
        vencida_tenant_2 = _solicitacao(
            tenant_id=OUTRO_TENANT, sla_deadline=momento - timedelta(hours=1)
        )
        governance = GovernanceEngine()

        disparados = verificar_sla_e_alarmar(
            [vencida_tenant_1, vencida_tenant_2], governance, agora_=momento
        )

        assert len(disparados) == 2
