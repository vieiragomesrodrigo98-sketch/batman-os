"""Testes de Rule Evolution (Vol.VI Cap.24) — AT-24.1 a AT-24.3."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from batman_os.foundation.types import (
    DecisionOption,
    EscalationPolicy,
    HumanReviewRef,
    Reversibilidade,
    RuleId,
    TenantId,
)
from batman_os.kernel.planning_engine import DecisionPoint
from batman_os.learning.knowledge_graph import KnowledgeGraph, TipoAresta, TipoNoKnowledge
from batman_os.learning.rule_evolution import (
    DecisionPointSignature,
    RuleCondition,
    RuleDefinition,
    RulePromotion,
    RuleResolutionAmbiguity,
    ShadowEvaluation,
    ShadowModeInsuficiente,
    StatusRegra,
    promover_a_active,
    resolve_rule,
    taxa_de_concordancia,
)

_APPROVED_BY = HumanReviewRef("review-1")
TENANT = TenantId("tenant-1")


def _politica() -> EscalationPolicy:
    return EscalationPolicy(
        confidence_threshold=0.8,
        preferred_escalation="human",
        max_llm_retries=1,
        reversibility=Reversibilidade.REVERSIVEL,
    )


def _ponto(pergunta: str = "qual acao para timeout?") -> DecisionPoint:
    return DecisionPoint(
        pergunta=pergunta,
        opcoes=[DecisionOption(id="a", descricao="A")],
        escalation_policy=_politica(),
    )


def _regra(
    id_: str,
    condicoes: list[RuleCondition] | None = None,
    version: str = "1.0.0",
    pergunta_padrao: str = "qual acao para timeout?",
    status: StatusRegra = StatusRegra.ACTIVE,
    reviewed_by: HumanReviewRef | None = _APPROVED_BY,
) -> RuleDefinition:
    return RuleDefinition(
        id=RuleId(id_),
        version=version,
        applies_to=DecisionPointSignature(pergunta_padrao=pergunta_padrao),
        condition=condicoes or [],
        resolution=DecisionOption(id="a", descricao="A"),
        confidence_base=0.9,
        provenance=RulePromotion(
            source_candidate_signature="sig-1",
            reviewed_by=reviewed_by,
        ),
        status=status,
    )


class TestAT241ShadowModeObrigatorioAntesDeActive:
    def test_avaliacoes_insuficientes_reprova(self) -> None:
        regra = _regra("R-1", status=StatusRegra.DRAFT)
        avaliacoes = [
            ShadowEvaluation(
                rule_id=regra.id,
                decision_point_id="dp-1",
                shadow_resolution=DecisionOption(id="a", descricao="A"),
                actual_resolution=DecisionOption(id="a", descricao="A"),
                agreement=True,
            )
        ]

        with pytest.raises(ShadowModeInsuficiente):
            promover_a_active(
                regra,
                avaliacoes,
                taxa_minima=0.9,
                minimo_avaliacoes=50,
                grafo=KnowledgeGraph(),
                tenant_id=TENANT,
            )

    def test_taxa_de_concordancia_abaixo_do_limiar_reprova(self) -> None:
        regra = _regra("R-1", status=StatusRegra.DRAFT)
        avaliacoes = [
            ShadowEvaluation(
                rule_id=regra.id,
                decision_point_id="dp-1",
                shadow_resolution=DecisionOption(id="a", descricao="A"),
                actual_resolution=DecisionOption(id="a", descricao="A"),
                agreement=i < 5,  # 5 de 10 = 50%
            )
            for i in range(10)
        ]

        with pytest.raises(ShadowModeInsuficiente):
            promover_a_active(
                regra,
                avaliacoes,
                taxa_minima=0.9,
                minimo_avaliacoes=10,
                grafo=KnowledgeGraph(),
                tenant_id=TENANT,
            )

    def test_avaliacoes_suficientes_e_concordantes_promove(self) -> None:
        regra = _regra("R-1", status=StatusRegra.DRAFT)
        avaliacoes = [
            ShadowEvaluation(
                rule_id=regra.id,
                decision_point_id="dp-1",
                shadow_resolution=DecisionOption(id="a", descricao="A"),
                actual_resolution=DecisionOption(id="a", descricao="A"),
                agreement=i < 48,  # 48 de 50 = 96%
            )
            for i in range(50)
        ]

        grafo = KnowledgeGraph()
        promovida = promover_a_active(
            regra, avaliacoes, taxa_minima=0.9, minimo_avaliacoes=50, grafo=grafo, tenant_id=TENANT
        )
        assert promovida.status == StatusRegra.ACTIVE

    def test_taxa_de_concordancia_vazia_e_zero(self) -> None:
        assert taxa_de_concordancia([]) == 0.0


class TestMilestone4RegraPromovidaEntraNoKnowledgeGraph:
    """Achado de revisão fechado na Milestone 4: antes, `promover_a_active`
    não escrevia no Knowledge Graph (Vol.VI Cap.23) — uma regra `active`
    nunca aparecia lá, apesar do Cap.26 descrever o ciclo completo passando
    por ele."""

    def _promover(self) -> tuple[RuleDefinition, KnowledgeGraph]:
        regra = _regra("R-graph", status=StatusRegra.DRAFT)
        avaliacoes = [
            ShadowEvaluation(
                rule_id=regra.id,
                decision_point_id="dp-1",
                shadow_resolution=DecisionOption(id="a", descricao="A"),
                actual_resolution=DecisionOption(id="a", descricao="A"),
                agreement=i < 48,
            )
            for i in range(50)
        ]
        grafo = KnowledgeGraph()
        promovida = promover_a_active(
            regra, avaliacoes, taxa_minima=0.9, minimo_avaliacoes=50, grafo=grafo, tenant_id=TENANT
        )
        return promovida, grafo

    def test_regra_promovida_vira_no_rule_no_grafo(self) -> None:
        promovida, grafo = self._promover()

        nos_rule = grafo.nos_por_tipo(TipoNoKnowledge.RULE)
        assert any(no.ref == str(promovida.id) for no in nos_rule)

    def test_regra_promovida_tem_aresta_justified_by(self) -> None:
        promovida, grafo = self._promover()

        no_regra = next(
            no for no in grafo.nos_por_tipo(TipoNoKnowledge.RULE) if no.ref == str(promovida.id)
        )
        vizinhos = grafo.get_neighbors(no_regra, edge_kind=TipoAresta.JUSTIFIED_BY)
        assert any(v.ref == str(promovida.provenance.reviewed_by) for v in vizinhos)

    def test_regra_promovida_tem_aresta_promoted_from(self) -> None:
        promovida, grafo = self._promover()

        no_regra = next(
            no for no in grafo.nos_por_tipo(TipoNoKnowledge.RULE) if no.ref == str(promovida.id)
        )
        vizinhos = grafo.get_neighbors(no_regra, edge_kind=TipoAresta.PROMOTED_FROM)
        assert any(v.ref == promovida.provenance.source_candidate_signature for v in vizinhos)

    def test_promocao_reprovada_nao_escreve_no_grafo(self) -> None:
        regra = _regra("R-reprovada", status=StatusRegra.DRAFT)
        avaliacoes = [
            ShadowEvaluation(
                rule_id=regra.id,
                decision_point_id="dp-1",
                shadow_resolution=DecisionOption(id="a", descricao="A"),
                actual_resolution=DecisionOption(id="a", descricao="A"),
                agreement=True,
            )
        ]
        grafo = KnowledgeGraph()

        with pytest.raises(ShadowModeInsuficiente):
            promover_a_active(
                regra,
                avaliacoes,
                taxa_minima=0.9,
                minimo_avaliacoes=50,
                grafo=grafo,
                tenant_id=TENANT,
            )

        assert grafo.nos_por_tipo(TipoNoKnowledge.RULE) == []


class TestAT242ReviewedByObrigatorioEstruturalmente:
    def test_construir_rule_promotion_sem_reviewed_by_falha(self) -> None:
        with pytest.raises(ValidationError):
            RulePromotion(source_candidate_signature="sig-1")  # type: ignore[call-arg]

    def test_construir_rule_definition_sem_reviewed_by_falha(self) -> None:
        with pytest.raises(ValidationError):
            _regra("R-1", reviewed_by=None)

    def test_com_reviewed_by_preenchido_funciona(self) -> None:
        regra = _regra("R-1")
        assert regra.provenance.reviewed_by == _APPROVED_BY


class TestAT243AmbiguidadeDeResolucaoDeRegra:
    def test_nenhuma_regra_casa_retorna_none(self) -> None:
        regra = _regra("R-1", condicoes=[RuleCondition(campo="servico", operador="eq", valor="x")])
        resultado = resolve_rule(_ponto(), dados={"servico": "y"}, candidatos=[regra])
        assert resultado is None

    def test_uma_unica_regra_e_retornada_direto(self) -> None:
        regra = _regra("R-1")
        resultado = resolve_rule(_ponto(), dados={}, candidatos=[regra])
        assert resultado is regra

    def test_maior_especificidade_desempata(self) -> None:
        generica = _regra("R-generica", condicoes=[])
        especifica = _regra(
            "R-especifica",
            condicoes=[RuleCondition(campo="servico", operador="eq", valor="gunicorn")],
        )

        resultado = resolve_rule(
            _ponto(), dados={"servico": "gunicorn"}, candidatos=[generica, especifica]
        )
        assert resultado is especifica

    def test_empate_real_de_especificidade_levanta_ambiguidade(self) -> None:
        r1 = _regra("R-1", condicoes=[RuleCondition(campo="servico", operador="eq", valor="x")])
        r2 = _regra("R-2", condicoes=[RuleCondition(campo="outro", operador="exists")])

        with pytest.raises(RuleResolutionAmbiguity):
            resolve_rule(_ponto(), dados={"servico": "x", "outro": True}, candidatos=[r1, r2])

    def test_regra_draft_nunca_e_considerada_na_resolucao(self) -> None:
        rascunho = _regra("R-1", status=StatusRegra.DRAFT)
        resultado = resolve_rule(_ponto(), dados={}, candidatos=[rascunho])
        assert resultado is None

    def test_signature_diferente_nunca_casa(self) -> None:
        regra = _regra("R-1", pergunta_padrao="outra pergunta")
        resultado = resolve_rule(_ponto(), dados={}, candidatos=[regra])
        assert resultado is None
