"""Vol. VI, Cap. 23 — Knowledge Graph.

Conecta todos os Knowledge Assets do Batman (regras, Capabilities, Skills,
Tools, Playbooks, ADRs, evidências, OperationalRecords) em um grafo
consultável — substrato sobre o qual Rule Evolution (Cap.24), Workflow
Evolution (Cap.25) e Operational Learning (Cap.26) operam.

ADR-0010: projeção derivada, nunca fonte de verdade paralela — nunca editado
diretamente, nunca consultado pelo Kernel em tempo real para decisões.

Fonte da verdade: docs/spec/06-learning/01-knowledge-graph.md
"""

from __future__ import annotations

from collections import deque
from datetime import timedelta
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from batman_os.foundation.types import MissionTypeId, PlaybookId, Timestamp, agora


class TipoNoKnowledge(StrEnum):
    """Vol.VI Cap.23, secao 23.3 — `KnowledgeNode.type`."""

    RULE = "rule"
    CAPABILITY = "capability"
    SKILL = "skill"
    TOOL = "tool"
    PLAYBOOK = "playbook"
    ADR = "adr"
    EVIDENCE = "evidence"
    OPERATIONAL_RECORD = "operational-record"


class KnowledgeNode(BaseModel):
    """Vol.VI Cap.23, secao 23.3 — `ref` é o ID opaco do Knowledge Asset
    (RuleId/CapabilityId/SkillId/... como string). Congelado (`frozen`) para
    servir de chave de dicionário/identidade em grafo."""

    model_config = ConfigDict(frozen=True)

    tipo: TipoNoKnowledge
    ref: str


class TipoAresta(StrEnum):
    """Vol.VI Cap.23, secao 23.3 — `KnowledgeEdge.kind`."""

    USES = "uses"
    INSTANTIATED_BY = "instantiated-by"
    PROMOTED_FROM = "promoted-from"
    JUSTIFIED_BY = "justified-by"
    SUPERSEDES = "supersedes"
    GOVERNED_BY = "governed-by"


class KnowledgeEdge(BaseModel):
    """Vol.VI Cap.23, secao 23.3."""

    model_config = ConfigDict(frozen=True)

    kind: TipoAresta
    de: KnowledgeNode
    para: KnowledgeNode


class KnowledgeNodeDetail(BaseModel):
    """Vol.VI Cap.23, secao 23.5 — payload associado a um nó no registro do
    grafo. `mission_type_id` só relevante para nós `playbook` (usado por
    `impact_analysis` para popular `affectedMissionTypes`, secao 23.5).
    `atualizado_em` usado por `detectar_drift` (AT-23.1)."""

    mission_type_id: MissionTypeId | None = None
    atualizado_em: Timestamp = Field(default_factory=agora)


class ImpactReport(BaseModel):
    """Vol.VI Cap.23, secao 23.5."""

    directly_dependent: list[KnowledgeNode] = Field(default_factory=list)
    transitively_dependent: list[KnowledgeNode] = Field(default_factory=list)
    affected_playbooks: list[PlaybookId] = Field(default_factory=list)
    affected_mission_types: list[MissionTypeId] = Field(default_factory=list)


class NoDesconhecido(Exception):
    """`get_node` chamado com uma referência não registrada."""


class KnowledgeGraph:
    """Vol.VI Cap.23, secao 23.5. Nunca editado diretamente por outro
    componente do Kernel/Runtime — só reconstruído/atualizado a partir dos
    catálogos-fonte já certificados (secao 23.6, ADR-0010)."""

    def __init__(self) -> None:
        self._nos: dict[KnowledgeNode, KnowledgeNodeDetail] = {}
        self._arestas: list[KnowledgeEdge] = []

    def adicionar_no(self, node: KnowledgeNode, detail: KnowledgeNodeDetail | None = None) -> None:
        self._nos[node] = detail or KnowledgeNodeDetail()

    def adicionar_aresta(self, edge: KnowledgeEdge) -> None:
        self._arestas.append(edge)

    def nos(self) -> list[KnowledgeNode]:
        return list(self._nos.keys())

    def nos_por_tipo(self, tipo: TipoNoKnowledge) -> list[KnowledgeNode]:
        return [n for n in self._nos if n.tipo == tipo]

    def get_node(self, ref: KnowledgeNode) -> KnowledgeNodeDetail:
        if ref not in self._nos:
            raise NoDesconhecido(f"No nao registrado no Knowledge Graph: {ref}")
        return self._nos[ref]

    def ultima_atualizacao(self, ref: KnowledgeNode) -> Timestamp | None:
        detail = self._nos.get(ref)
        return detail.atualizado_em if detail is not None else None

    def get_neighbors(
        self, ref: KnowledgeNode, edge_kind: TipoAresta | None = None
    ) -> list[KnowledgeNode]:
        return [
            e.para
            for e in self._arestas
            if e.de == ref and (edge_kind is None or e.kind == edge_kind)
        ]

    def impact_analysis(self, ref: KnowledgeNode) -> ImpactReport:
        """Vol.VI Cap.23, secao 23.5 (AT-23.2) — travessia REVERSA: quem
        aponta PARA `ref` (`Capability -uses-> Skill`: se a Skill muda,
        quem a usa é impactado) e transitivamente depende dele."""
        diretos = list({e.de for e in self._arestas if e.para == ref})

        visitados = set(diretos)
        fila: deque[KnowledgeNode] = deque(diretos)
        transitivos: list[KnowledgeNode] = []
        while fila:
            atual = fila.popleft()
            for anterior in {e.de for e in self._arestas if e.para == atual}:
                if anterior not in visitados:
                    visitados.add(anterior)
                    transitivos.append(anterior)
                    fila.append(anterior)

        todos_dependentes = diretos + transitivos
        playbooks: list[PlaybookId] = []
        mission_types: list[MissionTypeId] = []
        for no in todos_dependentes:
            if no.tipo != TipoNoKnowledge.PLAYBOOK:
                continue
            playbooks.append(PlaybookId(no.ref))
            detail = self._nos.get(no)
            if detail and detail.mission_type_id and detail.mission_type_id not in mission_types:
                mission_types.append(detail.mission_type_id)

        return ImpactReport(
            directly_dependent=diretos,
            transitively_dependent=transitivos,
            affected_playbooks=playbooks,
            affected_mission_types=mission_types,
        )

    def provenance_trail(self, ref: KnowledgeNode) -> list[KnowledgeNode]:
        """Vol.VI Cap.23, secao 23.5 — cadeia de `promoted-from`/`justified-by`
        até a origem. Cadeia quebrada (sem origem) retorna a trilha parcial
        encontrada, nunca lança — secao 23.7 trata isso como sinalização,
        não erro fatal de travessia."""
        trilha: list[KnowledgeNode] = []
        visitados = {ref}
        atual = ref
        while True:
            proximos = [
                e.para
                for e in self._arestas
                if e.de == atual and e.kind in (TipoAresta.PROMOTED_FROM, TipoAresta.JUSTIFIED_BY)
            ]
            if not proximos:
                break
            proximo = proximos[0]
            if proximo in visitados:
                break  # ciclo de proveniencia — erro de integridade, nao insiste
            trilha.append(proximo)
            visitados.add(proximo)
            atual = proximo
        return trilha


def verificar_integridade(grafo: KnowledgeGraph) -> list[str]:
    """Vol.VI Cap.23, secao 23.8 (AT-23.3) — nenhum nó `rule` pode existir
    sem ao menos uma aresta `justified-by` (Evidence First). Retorna a
    lista de violações (vazia se ok); não levanta — quem decide o que fazer
    com as violações é o chamador (mesmo padrão de `verificar_checklist`,
    Vol.IV Cap.16)."""
    violacoes: list[str] = []
    for no in grafo.nos_por_tipo(TipoNoKnowledge.RULE):
        tem_justificativa = bool(grafo.get_neighbors(no, edge_kind=TipoAresta.JUSTIFIED_BY))
        if not tem_justificativa:
            violacoes.append(f"Regra '{no.ref}' sem nenhuma aresta justified-by (Evidence First)")
    return violacoes


def detectar_drift(
    grafo: KnowledgeGraph,
    timestamps_fonte: dict[KnowledgeNode, Timestamp],
    sla: timedelta,
) -> list[KnowledgeNode]:
    """Vol.VI Cap.23, secao 23.7/23.8 (AT-23.1) — nós cujo catálogo-fonte
    mudou há mais tempo que o SLA de reconciliação sem que o grafo tenha
    sido atualizado (`ultima_atualizacao(no)` mais antiga que
    `timestamps_fonte[no] - sla`)."""
    desatualizados: list[KnowledgeNode] = []
    for no, ts_fonte in timestamps_fonte.items():
        ultima = grafo.ultima_atualizacao(no)
        if ultima is None or (ts_fonte - ultima) > sla:
            desatualizados.append(no)
    return desatualizados
