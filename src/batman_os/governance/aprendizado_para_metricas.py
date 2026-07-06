"""Vol. VII, Cap. 30 — ponte Governance -> Learning para o painel
`learning-throughput`.

Achado de revisão (Milestone 4 desta construção): `ObservabilityEngine`
(Cap.30) já cataloga as métricas `tamanho-knowledge-graph` e
`regras-promovidas-por-periodo`, mas nada alimentava `registrar_serie()`
a partir do Knowledge Graph (Cap.23) / Rule Evolution (Cap.24) de verdade
— o painel `learning-throughput` existia só como entrada vazia no catálogo.

Excecao deliberada ao grafo de dependencias do Vol.VIII Cap.32, secao 32.3
(mesmo raciocinio de `learning/rule_evolution_adapter.py`): `governance ->
learning` é aresta permitida (Governance/Observability é projeção derivada
de TODOS os catálogos-fonte, Cap.30 secao 30.2) — só este módulo, cuja
única razão de existir é a integração, importa `learning.knowledge_graph`/
`learning.rule_evolution` diretamente dentro de `governance/`.
"""

from __future__ import annotations

from datetime import timedelta

from batman_os.foundation.types import Timestamp, agora
from batman_os.governance.observability_engine import (
    MetricId,
    ObservabilityEngine,
    PontoDeSerie,
    construir_serie,
)
from batman_os.learning.knowledge_graph import KnowledgeGraph
from batman_os.learning.rule_evolution import RuleDefinition, StatusRegra

METRIC_TAMANHO_KNOWLEDGE_GRAPH = MetricId("tamanho-knowledge-graph")
METRIC_REGRAS_PROMOVIDAS = MetricId("regras-promovidas-por-periodo")


def alimentar_metricas_de_aprendizado(
    observability: ObservabilityEngine,
    grafo: KnowledgeGraph,
    regras: list[RuleDefinition],
    janela_agregacao: timedelta,
    agora_: Timestamp | None = None,
) -> None:
    """Vol.VII Cap.30, secao 30.3 — calcula os dois pontos de série do
    painel `learning-throughput` a partir do estado ATUAL do Knowledge
    Graph e do catálogo de `RuleDefinition`s, e os registra no
    `ObservabilityEngine`. Não recalcula histórico — cada chamada produz
    um ponto no `agora_` (ou o momento real, se omitido); quem chama
    decide a cadência de amostragem (mesmo espírito de `construir_serie`,
    que é pura sobre os pontos que recebe)."""
    momento = agora_ or agora()

    serie_tamanho_grafo = construir_serie(
        METRIC_TAMANHO_KNOWLEDGE_GRAPH,
        [PontoDeSerie(timestamp=momento, value=float(len(grafo.nos())))],
        janela_agregacao,
    )
    observability.registrar_serie(serie_tamanho_grafo)

    promovidas = sum(1 for r in regras if r.status == StatusRegra.ACTIVE)
    serie_regras_promovidas = construir_serie(
        METRIC_REGRAS_PROMOVIDAS,
        [PontoDeSerie(timestamp=momento, value=float(promovidas))],
        janela_agregacao,
    )
    observability.registrar_serie(serie_regras_promovidas)
