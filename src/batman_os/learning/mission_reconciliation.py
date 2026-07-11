"""Vol. VI, Cap. 23 (extensão) — Mission Graph.

Fase 4, Estágio 4.2 do roadmap de plataforma (`.claude/plans/peaceful-
wondering-hearth.md`): reconciliador que estende o Knowledge Graph para
registrar Missões e Decisions — não um grafo novo. Mesmo padrão de
escrita que Rule Evolution (Cap.24) e Workflow Evolution (Cap.25) já
usam: `adicionar_no`/`adicionar_aresta` DIRETO, com objetos que o
chamador já tem em mãos, nunca replay do EventBus (achado real: o
`DecisionEngine` nunca publica `Decision.evidence` no EventBus — isso
NÃO é pré-requisito aqui, porque o chamador da Missão já recebe o
`Decision` completo direto de `decision_engine.resolve()`).

Protocols locais (não importa `kernel.mission_runtime.Mission`/
`kernel.decision_engine.Decision` diretamente) — mesmo raciocínio de
`DecisionPointComoAssinatura` em `learning/rule_evolution.py`: `learning`
depende de `shared`/`runtime`/`workflow`, nunca de `kernel` (Vol.VIII
Cap.32, secao 32.3).

Reconcilia Missões `completed` E `failed` igualmente — o grafo é trilha
de auditoria, não só de sucesso.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from batman_os.foundation.types import MissionId, PlaybookId, TenantId
from batman_os.learning.knowledge_graph import (
    KnowledgeEdge,
    KnowledgeGraph,
    KnowledgeNode,
    TipoAresta,
    TipoNoKnowledge,
)


class EvidenciaReconciliavel(Protocol):
    """Forma mínima de `kernel.decision_engine.Evidence` necessária para
    reconciliação."""

    @property
    def origem(self) -> str: ...


class DecisaoReconciliavel(Protocol):
    """Forma mínima de `kernel.decision_engine.Decision` necessária para
    reconciliação."""

    @property
    def id(self) -> str: ...

    @property
    def evidence(self) -> Sequence[EvidenciaReconciliavel]: ...


class MissaoReconciliavel(Protocol):
    """Forma mínima de `kernel.mission_runtime.Mission` necessária para
    reconciliação."""

    @property
    def id(self) -> MissionId: ...

    @property
    def tenant_id(self) -> TenantId: ...


def reconciliar_missao(
    missao: MissaoReconciliavel,
    decisoes: Sequence[DecisaoReconciliavel],
    grafo: KnowledgeGraph,
    *,
    playbook_id: PlaybookId | None = None,
) -> None:
    """Registra a Missão no Knowledge Graph: nó `MISSION`; se
    `playbook_id` fornecido, nó `PLAYBOOK` + aresta `USES`
    (Missão->Playbook); para cada Decision, nó `DECISION` + aresta
    `PRODUCED` (Missão->Decision) + um nó `EVIDENCE` por origem distinta
    em `decisao.evidence` (dedup — a mesma origem não vira nó duplicado)
    + aresta `JUSTIFIED_BY` (Decision->Evidence)."""
    no_missao = KnowledgeNode(
        tipo=TipoNoKnowledge.MISSION, ref=str(missao.id), tenant_id=missao.tenant_id
    )
    grafo.adicionar_no(no_missao)

    if playbook_id is not None:
        no_playbook = KnowledgeNode(
            tipo=TipoNoKnowledge.PLAYBOOK, ref=str(playbook_id), tenant_id=missao.tenant_id
        )
        grafo.adicionar_no(no_playbook)
        grafo.adicionar_aresta(
            KnowledgeEdge(
                kind=TipoAresta.USES,
                de=no_missao,
                para=no_playbook,
                tenant_id=missao.tenant_id,
            )
        )

    for decisao in decisoes:
        no_decisao = KnowledgeNode(
            tipo=TipoNoKnowledge.DECISION, ref=str(decisao.id), tenant_id=missao.tenant_id
        )
        grafo.adicionar_no(no_decisao)
        grafo.adicionar_aresta(
            KnowledgeEdge(
                kind=TipoAresta.PRODUCED,
                de=no_missao,
                para=no_decisao,
                tenant_id=missao.tenant_id,
            )
        )

        origens_vistas: set[str] = set()
        for evidencia in decisao.evidence:
            if evidencia.origem in origens_vistas:
                continue
            origens_vistas.add(evidencia.origem)
            no_evidencia = KnowledgeNode(
                tipo=TipoNoKnowledge.EVIDENCE, ref=evidencia.origem, tenant_id=missao.tenant_id
            )
            grafo.adicionar_no(no_evidencia)
            grafo.adicionar_aresta(
                KnowledgeEdge(
                    kind=TipoAresta.JUSTIFIED_BY,
                    de=no_decisao,
                    para=no_evidencia,
                    tenant_id=missao.tenant_id,
                )
            )
