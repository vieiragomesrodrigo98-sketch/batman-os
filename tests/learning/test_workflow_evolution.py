"""Testes de Workflow Evolution (Vol.VI Cap.25) — AT-25.1 a AT-25.3."""

from __future__ import annotations

from datetime import timedelta

import pytest

from batman_os.foundation.types import (
    CapabilityId,
    CapabilityRef,
    DateRange,
    HumanReviewRef,
    MissionTypeId,
    PlaybookId,
    ProposalId,
    RecoveryStrategy,
    TenantId,
    TipoRecoveryStrategy,
    agora,
)
from batman_os.kernel.planning_engine import PlanStepTemplate
from batman_os.learning.knowledge_graph import KnowledgeGraph, TipoAresta, TipoNoKnowledge
from batman_os.learning.workflow_evolution import (
    CoberturaDeRecoveryReduzida,
    EvolutionEvidence,
    PropostaNaoAprovada,
    RevisaoHumanaObrigatoriaParaProposta,
    StatusProposta,
    TipoProposta,
    WorkflowEvolutionProposal,
    aplicar_proposta,
    depreciar_por_desuso,
    deveria_propor_depreciacao_por_desuso,
    deveria_propor_inversao_de_fallback,
    verificar_cobertura_de_merge,
)
from batman_os.workflow.playbooks import (
    GapDeCertificacaoDoPlaybook,
    IntentMatcher,
    PlaybookDefinition,
    PlaybookProvenance,
    StatusPlaybook,
)

_APPROVED_BY = HumanReviewRef("review-1")
TIPO = MissionTypeId("investigate-incident")
TENANT = TenantId("tenant-1")


def _evidencia() -> EvolutionEvidence:
    agora_ = agora()
    return EvolutionEvidence(
        execution_sample_size=100,
        observation_window=DateRange(inicio=agora_ - timedelta(days=30), fim=agora_),
        metrics_snapshot={"fallbackRate": 0.87},
    )


def _playbook(
    id_: str,
    steps_template: list[PlanStepTemplate] | None = None,
    recovery_defaults: dict[int, RecoveryStrategy] | None = None,
    status: StatusPlaybook = StatusPlaybook.ACTIVE,
) -> PlaybookDefinition:
    return PlaybookDefinition(
        id=PlaybookId(id_),
        version="1.0.0",
        applies_to=IntentMatcher(),
        mission_type_id=TIPO,
        priority=1,
        steps_template=steps_template or [],
        recovery_defaults=recovery_defaults or {},
        status=status,
        provenance=PlaybookProvenance(origin="hand-authored", approved_by=_APPROVED_BY),
    )


def _proposta(
    kind: TipoProposta = TipoProposta.INVERT_FALLBACK,
    proposed_change: list[PlaybookDefinition] | None = None,
    reviewed_by: HumanReviewRef | None = _APPROVED_BY,
    status: StatusProposta = StatusProposta.APPROVED,
) -> WorkflowEvolutionProposal:
    return WorkflowEvolutionProposal(
        id=ProposalId("prop-1"),
        kind=kind,
        affected_playbooks=[PlaybookId("pb-original")],
        evidence=_evidencia(),
        proposed_change=proposed_change or [_playbook("pb-novo")],
        reviewed_by=reviewed_by,
        status=status,
    )


class TestAT251NuncaAplicaSemCertificacaoCompleta:
    def test_sem_human_review_nunca_aplica(self) -> None:
        proposta = _proposta(reviewed_by=None)

        with pytest.raises(RevisaoHumanaObrigatoriaParaProposta):
            aplicar_proposta(
                proposta, certificar=lambda pb: pb, grafo=KnowledgeGraph(), tenant_id=TENANT
            )

    def test_proposta_nao_aprovada_nao_pode_ser_aplicada(self) -> None:
        proposta = _proposta(status=StatusProposta.PROPOSED)

        with pytest.raises(PropostaNaoAprovada):
            aplicar_proposta(
                proposta, certificar=lambda pb: pb, grafo=KnowledgeGraph(), tenant_id=TENANT
            )

    def test_certificacao_bem_sucedida_aplica(self) -> None:
        proposta = _proposta()

        def certificar_ok(pb: PlaybookDefinition) -> PlaybookDefinition:
            return pb.model_copy(update={"status": StatusPlaybook.ACTIVE})

        resultado = aplicar_proposta(
            proposta, certificar=certificar_ok, grafo=KnowledgeGraph(), tenant_id=TENANT
        )

        assert resultado.proposta.status == StatusProposta.APPLIED
        assert len(resultado.playbooks_certificados) == 1
        assert resultado.motivo_rejeicao is None

    def test_falha_de_certificacao_nunca_aplica_parcialmente(self) -> None:
        proposta = _proposta()

        def certificar_falha(pb: PlaybookDefinition) -> PlaybookDefinition:
            raise GapDeCertificacaoDoPlaybook(f"Playbook '{pb.id}' reprovado: motivo de teste")

        resultado = aplicar_proposta(
            proposta, certificar=certificar_falha, grafo=KnowledgeGraph(), tenant_id=TENANT
        )

        assert resultado.proposta.status == StatusProposta.REJECTED
        assert resultado.playbooks_certificados == []
        assert resultado.motivo_rejeicao is not None
        assert "reprovado" in resultado.motivo_rejeicao

    def test_falha_de_certificacao_preserva_evidencia_original_e_anexa_falha(self) -> None:
        proposta = _proposta()

        def certificar_falha(pb: PlaybookDefinition) -> PlaybookDefinition:
            raise GapDeCertificacaoDoPlaybook(f"Playbook '{pb.id}' reprovado")

        resultado = aplicar_proposta(
            proposta, certificar=certificar_falha, grafo=KnowledgeGraph(), tenant_id=TENANT
        )

        assert resultado.proposta.evidence.metrics_snapshot["fallbackRate"] == 0.87
        assert resultado.proposta.evidence.metrics_snapshot["certification_failure"] == 1.0


class TestMilestone4PropostaAplicadaEntraNoKnowledgeGraph:
    """Achado de revisão fechado na Milestone 4: `aplicar_proposta` não
    escrevia no Knowledge Graph (Vol.VI Cap.23) — um Playbook certificado
    via evolução nunca aparecia lá."""

    def test_playbook_certificado_vira_no_playbook_no_grafo(self) -> None:
        proposta = _proposta()
        grafo = KnowledgeGraph()

        def certificar_ok(pb: PlaybookDefinition) -> PlaybookDefinition:
            return pb.model_copy(update={"status": StatusPlaybook.ACTIVE})

        aplicar_proposta(proposta, certificar=certificar_ok, grafo=grafo, tenant_id=TENANT)

        nos_playbook = grafo.nos_por_tipo(TipoNoKnowledge.PLAYBOOK)
        assert any(no.ref == "pb-novo" for no in nos_playbook)

    def test_playbook_certificado_tem_aresta_justified_by(self) -> None:
        proposta = _proposta()
        grafo = KnowledgeGraph()

        def certificar_ok(pb: PlaybookDefinition) -> PlaybookDefinition:
            return pb.model_copy(update={"status": StatusPlaybook.ACTIVE})

        aplicar_proposta(proposta, certificar=certificar_ok, grafo=grafo, tenant_id=TENANT)

        no_novo = next(
            no for no in grafo.nos_por_tipo(TipoNoKnowledge.PLAYBOOK) if no.ref == "pb-novo"
        )
        vizinhos = grafo.get_neighbors(no_novo, edge_kind=TipoAresta.JUSTIFIED_BY)
        assert any(v.ref == str(_APPROVED_BY) for v in vizinhos)

    def test_playbook_certificado_supersede_o_playbook_afetado(self) -> None:
        proposta = _proposta()
        grafo = KnowledgeGraph()

        def certificar_ok(pb: PlaybookDefinition) -> PlaybookDefinition:
            return pb.model_copy(update={"status": StatusPlaybook.ACTIVE})

        aplicar_proposta(proposta, certificar=certificar_ok, grafo=grafo, tenant_id=TENANT)

        no_novo = next(
            no for no in grafo.nos_por_tipo(TipoNoKnowledge.PLAYBOOK) if no.ref == "pb-novo"
        )
        vizinhos = grafo.get_neighbors(no_novo, edge_kind=TipoAresta.SUPERSEDES)
        assert any(v.ref == "pb-original" for v in vizinhos)

    def test_proposta_rejeitada_nao_escreve_no_grafo(self) -> None:
        proposta = _proposta()
        grafo = KnowledgeGraph()

        def certificar_falha(pb: PlaybookDefinition) -> PlaybookDefinition:
            raise GapDeCertificacaoDoPlaybook(f"Playbook '{pb.id}' reprovado")

        aplicar_proposta(proposta, certificar=certificar_falha, grafo=grafo, tenant_id=TENANT)

        assert grafo.nos_por_tipo(TipoNoKnowledge.PLAYBOOK) == []


class TestAT252FusaoNuncaReduzCoberturaDeRecovery:
    def _template(self, capability_id: str) -> PlanStepTemplate:
        return PlanStepTemplate(
            capability=CapabilityRef(capability_id=CapabilityId(capability_id), versao="1.0.0")
        )

    def test_fusao_preservando_cobertura_passa(self) -> None:
        recovery = RecoveryStrategy(tipo=TipoRecoveryStrategy.RETRY, max_tentativas=3)
        original_a = _playbook(
            "pb-a",
            steps_template=[self._template("cap-x")],
            recovery_defaults={0: recovery},
        )
        original_b = _playbook(
            "pb-b",
            steps_template=[self._template("cap-y")],
            recovery_defaults={0: recovery},
        )
        fundido = _playbook(
            "pb-fundido",
            steps_template=[self._template("cap-x"), self._template("cap-y")],
            recovery_defaults={0: recovery, 1: recovery},
        )

        verificar_cobertura_de_merge([original_a, original_b], fundido)  # nao levanta

    def test_fusao_perdendo_cobertura_de_uma_capability_falha(self) -> None:
        recovery = RecoveryStrategy(tipo=TipoRecoveryStrategy.RETRY, max_tentativas=3)
        original_a = _playbook(
            "pb-a", steps_template=[self._template("cap-x")], recovery_defaults={0: recovery}
        )
        original_b = _playbook(
            "pb-b", steps_template=[self._template("cap-y")], recovery_defaults={0: recovery}
        )
        fundido_incompleto = _playbook(
            "pb-fundido",
            steps_template=[self._template("cap-x"), self._template("cap-y")],
            recovery_defaults={0: recovery},  # cap-y perdeu a cobertura
        )

        with pytest.raises(CoberturaDeRecoveryReduzida):
            verificar_cobertura_de_merge([original_a, original_b], fundido_incompleto)

    def test_identidade_por_capability_nao_por_indice(self) -> None:
        """A mesma Capability aparecendo em indices diferentes entre
        original e fundido ainda conta como coberta."""
        recovery = RecoveryStrategy(tipo=TipoRecoveryStrategy.RETRY, max_tentativas=3)
        original = _playbook(
            "pb-a", steps_template=[self._template("cap-x")], recovery_defaults={0: recovery}
        )
        fundido = _playbook(
            "pb-fundido",
            steps_template=[self._template("cap-outra"), self._template("cap-x")],
            recovery_defaults={1: recovery},  # cap-x agora no indice 1
        )

        verificar_cobertura_de_merge([original], fundido)  # nao levanta


class TestAT253DepreciacaoNuncaRemoveFisicamente:
    def test_depreciar_muda_apenas_o_status(self) -> None:
        playbook = _playbook("pb-1")
        depreciado = depreciar_por_desuso(playbook)

        assert depreciado.status == StatusPlaybook.DEPRECATED
        assert depreciado.id == playbook.id
        assert depreciado.steps_template == playbook.steps_template
        assert depreciado.provenance == playbook.provenance

    def test_playbook_original_nao_e_mutado(self) -> None:
        playbook = _playbook("pb-1")
        depreciar_por_desuso(playbook)

        assert playbook.status == StatusPlaybook.ACTIVE


class TestSinaisDeEvolucao:
    def test_fallback_rate_alto_com_volume_suficiente_propoe_inversao(self) -> None:
        assert (
            deveria_propor_inversao_de_fallback(
                fallback_rate=0.87, limiar=0.7, execucoes_observadas=100, minimo_execucoes=50
            )
            is True
        )

    def test_fallback_rate_alto_mas_volume_insuficiente_nao_propoe(self) -> None:
        assert (
            deveria_propor_inversao_de_fallback(
                fallback_rate=0.9, limiar=0.7, execucoes_observadas=10, minimo_execucoes=50
            )
            is False
        )

    def test_fallback_rate_abaixo_do_limiar_nao_propoe(self) -> None:
        assert (
            deveria_propor_inversao_de_fallback(
                fallback_rate=0.3, limiar=0.7, execucoes_observadas=100, minimo_execucoes=50
            )
            is False
        )

    def test_desuso_alem_da_janela_propoe_depreciacao(self) -> None:
        assert deveria_propor_depreciacao_por_desuso(200, janela_dias=180) is True

    def test_desuso_dentro_da_janela_nao_propoe(self) -> None:
        assert deveria_propor_depreciacao_por_desuso(100, janela_dias=180) is False
