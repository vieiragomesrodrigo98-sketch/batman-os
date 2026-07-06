"""Testes da ponte Governance -> Learning (Vol.VII Cap.30, Milestone 4).

Prova que o painel `learning-throughput` deixa de ser uma entrada vazia no
catálogo: `tamanho-knowledge-graph` e `regras-promovidas-por-periodo`
passam a refletir o estado real do Knowledge Graph e do catálogo de
`RuleDefinition`s.
"""

from __future__ import annotations

from datetime import timedelta

from batman_os.foundation.types import DecisionOption, HumanReviewRef, RuleId
from batman_os.governance.aprendizado_para_metricas import (
    METRIC_REGRAS_PROMOVIDAS,
    METRIC_TAMANHO_KNOWLEDGE_GRAPH,
    alimentar_metricas_de_aprendizado,
)
from batman_os.governance.governance_engine import GovernanceEngine
from batman_os.governance.observability_engine import NomeDoPainel, ObservabilityEngine
from batman_os.learning.knowledge_graph import (
    KnowledgeGraph,
    KnowledgeNode,
    TipoNoKnowledge,
)
from batman_os.learning.rule_evolution import (
    DecisionPointSignature,
    RuleDefinition,
    RulePromotion,
    StatusRegra,
)

_JANELA = timedelta(hours=1)


def _regra(id_: str, status: StatusRegra) -> RuleDefinition:
    return RuleDefinition(
        id=RuleId(id_),
        version="1.0.0",
        applies_to=DecisionPointSignature(pergunta_padrao="qual acao?"),
        condition=[],
        resolution=DecisionOption(id="a", descricao="A"),
        confidence_base=0.9,
        provenance=RulePromotion(
            source_candidate_signature="sig-1", reviewed_by=HumanReviewRef("review-1")
        ),
        status=status,
    )


def _observability() -> ObservabilityEngine:
    return ObservabilityEngine(governance=GovernanceEngine())


class TestTamanhoDoKnowledgeGraph:
    def test_reflete_a_quantidade_real_de_nos(self) -> None:
        grafo = KnowledgeGraph()
        grafo.adicionar_no(KnowledgeNode(tipo=TipoNoKnowledge.RULE, ref="R-1"))
        grafo.adicionar_no(KnowledgeNode(tipo=TipoNoKnowledge.RULE, ref="R-2"))
        observability = _observability()

        alimentar_metricas_de_aprendizado(observability, grafo, [], _JANELA)

        serie = observability.get_metric(METRIC_TAMANHO_KNOWLEDGE_GRAPH)
        assert serie is not None
        assert serie.points[0].value == 2.0

    def test_grafo_vazio_produz_zero(self) -> None:
        observability = _observability()

        alimentar_metricas_de_aprendizado(observability, KnowledgeGraph(), [], _JANELA)

        serie = observability.get_metric(METRIC_TAMANHO_KNOWLEDGE_GRAPH)
        assert serie is not None
        assert serie.points[0].value == 0.0


class TestRegrasPromovidasPorPeriodo:
    def test_conta_so_regras_active(self) -> None:
        regras = [
            _regra("R-1", StatusRegra.ACTIVE),
            _regra("R-2", StatusRegra.ACTIVE),
            _regra("R-3", StatusRegra.DRAFT),
            _regra("R-4", StatusRegra.DEPRECATED),
        ]
        observability = _observability()

        alimentar_metricas_de_aprendizado(observability, KnowledgeGraph(), regras, _JANELA)

        serie = observability.get_metric(METRIC_REGRAS_PROMOVIDAS)
        assert serie is not None
        assert serie.points[0].value == 2.0

    def test_sem_regras_ativas_produz_zero(self) -> None:
        regras = [_regra("R-1", StatusRegra.DRAFT)]
        observability = _observability()

        alimentar_metricas_de_aprendizado(observability, KnowledgeGraph(), regras, _JANELA)

        serie = observability.get_metric(METRIC_REGRAS_PROMOVIDAS)
        assert serie is not None
        assert serie.points[0].value == 0.0


class TestIntegracaoComOPainel:
    def test_metricas_aparecem_no_painel_learning_throughput(self) -> None:
        grafo = KnowledgeGraph()
        grafo.adicionar_no(KnowledgeNode(tipo=TipoNoKnowledge.RULE, ref="R-1"))
        regras = [_regra("R-1", StatusRegra.ACTIVE)]
        observability = _observability()

        alimentar_metricas_de_aprendizado(observability, grafo, regras, _JANELA)

        painel = observability.get_dashboard(NomeDoPainel.LEARNING_THROUGHPUT)
        assert METRIC_TAMANHO_KNOWLEDGE_GRAPH in painel
        assert METRIC_REGRAS_PROMOVIDAS in painel
