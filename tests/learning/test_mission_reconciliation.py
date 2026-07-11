"""Testes do Mission Graph (Fase 4, Estágios 4.2/4.3) — `reconciliar_missao`."""

from __future__ import annotations

from dataclasses import dataclass, field

from batman_os.foundation.types import MissionId, PlaybookId, TenantId
from batman_os.learning.knowledge_graph import KnowledgeGraph, TipoAresta, TipoNoKnowledge
from batman_os.learning.mission_reconciliation import reconciliar_missao

TENANT = TenantId("tenant-1")


@dataclass(frozen=True)
class _EvidenciaFake:
    origem: str


@dataclass(frozen=True)
class _DecisaoFake:
    id: str
    evidence: list[_EvidenciaFake] = field(default_factory=list)


@dataclass(frozen=True)
class _MissaoFake:
    id: MissionId
    tenant_id: TenantId


class TestReconciliarMissaoComDecisoesEPlaybook:
    def test_cria_um_no_de_cada_tipo_esperado(self) -> None:
        missao = _MissaoFake(id=MissionId("m-1"), tenant_id=TENANT)
        decisao_a = _DecisaoFake(id="d-1", evidence=[_EvidenciaFake(origem="regra-x")])
        decisao_b = _DecisaoFake(id="d-2", evidence=[_EvidenciaFake(origem="regra-x")])
        grafo = KnowledgeGraph()

        reconciliar_missao(missao, [decisao_a, decisao_b], grafo, playbook_id=PlaybookId("pb-1"))

        assert len(grafo.nos_por_tipo(TipoNoKnowledge.MISSION)) == 1
        assert len(grafo.nos_por_tipo(TipoNoKnowledge.PLAYBOOK)) == 1
        assert len(grafo.nos_por_tipo(TipoNoKnowledge.DECISION)) == 2
        # As 2 decisions referenciam a MESMA origem ("regra-x") — dedup
        # global via identidade estrutural do KnowledgeNode, não 2 nós.
        assert len(grafo.nos_por_tipo(TipoNoKnowledge.EVIDENCE)) == 1

    def test_arestas_conectam_missao_playbook_decision_e_evidencia(self) -> None:
        missao = _MissaoFake(id=MissionId("m-1"), tenant_id=TENANT)
        decisao = _DecisaoFake(id="d-1", evidence=[_EvidenciaFake(origem="regra-x")])
        grafo = KnowledgeGraph()

        reconciliar_missao(missao, [decisao], grafo, playbook_id=PlaybookId("pb-1"))

        no_missao = next(n for n in grafo.nos_por_tipo(TipoNoKnowledge.MISSION) if n.ref == "m-1")
        no_playbook = next(
            n for n in grafo.nos_por_tipo(TipoNoKnowledge.PLAYBOOK) if n.ref == "pb-1"
        )
        no_decisao = next(n for n in grafo.nos_por_tipo(TipoNoKnowledge.DECISION) if n.ref == "d-1")
        no_evidencia = next(
            n for n in grafo.nos_por_tipo(TipoNoKnowledge.EVIDENCE) if n.ref == "regra-x"
        )

        assert grafo.get_neighbors(no_missao, edge_kind=TipoAresta.USES) == [no_playbook]
        assert grafo.get_neighbors(no_missao, edge_kind=TipoAresta.PRODUCED) == [no_decisao]
        assert grafo.get_neighbors(no_decisao, edge_kind=TipoAresta.JUSTIFIED_BY) == [no_evidencia]

    def test_provenance_trail_navega_da_decision_ate_a_evidencia(self) -> None:
        missao = _MissaoFake(id=MissionId("m-1"), tenant_id=TENANT)
        decisao = _DecisaoFake(id="d-1", evidence=[_EvidenciaFake(origem="regra-x")])
        grafo = KnowledgeGraph()

        reconciliar_missao(missao, [decisao], grafo, playbook_id=PlaybookId("pb-1"))

        no_decisao = next(n for n in grafo.nos_por_tipo(TipoNoKnowledge.DECISION) if n.ref == "d-1")
        no_evidencia = next(
            n for n in grafo.nos_por_tipo(TipoNoKnowledge.EVIDENCE) if n.ref == "regra-x"
        )

        assert grafo.provenance_trail(no_decisao) == [no_evidencia]

    def test_tenant_id_do_missao_e_propagado_a_todo_no_e_aresta(self) -> None:
        outro_tenant = TenantId("tenant-2")
        missao = _MissaoFake(id=MissionId("m-1"), tenant_id=outro_tenant)
        decisao = _DecisaoFake(id="d-1", evidence=[_EvidenciaFake(origem="regra-x")])
        grafo = KnowledgeGraph()

        reconciliar_missao(missao, [decisao], grafo, playbook_id=PlaybookId("pb-1"))

        assert all(n.tenant_id == outro_tenant for n in grafo.nos())


class TestReconciliarMissaoSemDecisoes:
    def test_sem_decisoes_cria_apenas_missao_playbook_e_uses_sem_erro(self) -> None:
        missao = _MissaoFake(id=MissionId("m-1"), tenant_id=TENANT)
        grafo = KnowledgeGraph()

        reconciliar_missao(missao, [], grafo, playbook_id=PlaybookId("pb-1"))

        assert len(grafo.nos_por_tipo(TipoNoKnowledge.MISSION)) == 1
        assert len(grafo.nos_por_tipo(TipoNoKnowledge.PLAYBOOK)) == 1
        assert grafo.nos_por_tipo(TipoNoKnowledge.DECISION) == []
        assert grafo.nos_por_tipo(TipoNoKnowledge.EVIDENCE) == []

    def test_sem_playbook_id_cria_apenas_a_missao(self) -> None:
        missao = _MissaoFake(id=MissionId("m-1"), tenant_id=TENANT)
        grafo = KnowledgeGraph()

        reconciliar_missao(missao, [], grafo)

        assert len(grafo.nos_por_tipo(TipoNoKnowledge.MISSION)) == 1
        assert grafo.nos_por_tipo(TipoNoKnowledge.PLAYBOOK) == []


class TestReconciliarMissaoDecisaoSemEvidenciaDuplicada:
    def test_mesma_origem_repetida_na_mesma_decision_nao_duplica_no(self) -> None:
        missao = _MissaoFake(id=MissionId("m-1"), tenant_id=TENANT)
        decisao = _DecisaoFake(
            id="d-1",
            evidence=[_EvidenciaFake(origem="regra-x"), _EvidenciaFake(origem="regra-x")],
        )
        grafo = KnowledgeGraph()

        reconciliar_missao(missao, [decisao], grafo)

        assert len(grafo.nos_por_tipo(TipoNoKnowledge.EVIDENCE)) == 1
