"""Vol. VI, Cap. 25 — Workflow Evolution.

Enquanto o Cap.24 especificou como `DecisionPoint`s individuais evoluem
para regras, este capítulo especifica como Playbooks inteiros evoluem —
inversão de fallback, fusão, depreciação por desuso — sempre com base em
evidência real de execução, nunca em intuição de design, e sempre passando
pela certificação completa de Playbook (Vol.V Cap.21), mesmo quando a
evidência parece "óbvia".

Fonte da verdade: docs/spec/06-learning/03-workflow-evolution.md
"""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum

from pydantic import BaseModel, Field

from batman_os.foundation.types import (
    CapabilityId,
    DateRange,
    HumanReviewRef,
    PlaybookId,
    ProposalId,
)
from batman_os.learning.knowledge_graph import (
    KnowledgeEdge,
    KnowledgeGraph,
    KnowledgeNode,
    TipoAresta,
    TipoNoKnowledge,
)
from batman_os.workflow.playbooks import (
    GapDeCertificacaoDoPlaybook,
    PlaybookDefinition,
    StatusPlaybook,
)


class TipoProposta(StrEnum):
    """Vol.VI Cap.25, secao 25.3 — `WorkflowEvolutionProposal.kind`."""

    INVERT_FALLBACK = "invert-fallback"
    MERGE_PLAYBOOKS = "merge-playbooks"
    SPLIT_PLAYBOOK = "split-playbook"
    DEPRECATE_PLAYBOOK = "deprecate-playbook"


class StatusProposta(StrEnum):
    """Vol.VI Cap.25, secao 25.3."""

    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"


class EvolutionEvidence(BaseModel):
    """Vol.VI Cap.25, secao 25.3."""

    execution_sample_size: int
    observation_window: DateRange
    metrics_snapshot: dict[str, float] = Field(default_factory=dict)


class WorkflowEvolutionProposal(BaseModel):
    """Vol.VI Cap.25, secao 25.3.

    Nota de implementação: `proposedChange` da especificação é
    `PlaybookDefinition | PlaybookDefinition[]` (união); normalizado aqui
    como `list[PlaybookDefinition]` sempre — um elemento para `invert-
    fallback`/`split-playbook`/`deprecate-playbook`, dois ou mais para
    `merge-playbooks` (gap mecânico de tipagem, não decisão nova)."""

    id: ProposalId
    kind: TipoProposta
    affected_playbooks: list[PlaybookId]
    evidence: EvolutionEvidence
    proposed_change: list[PlaybookDefinition]
    reviewed_by: HumanReviewRef | None = None
    status: StatusProposta = StatusProposta.PROPOSED


class RevisaoHumanaObrigatoriaParaProposta(Exception):
    """Vol.VI Cap.25, secao 25.4 — nenhuma proposta é aplicada sem Human
    Review, mesmo quando a evidência parece "óbvia" (nota crítica secao 25.4)."""


class PropostaNaoAprovada(Exception):
    """Só é aplicável uma proposta com `status: approved`."""


class ResultadoAplicacao(BaseModel):
    """Vol.VI Cap.25, secao 25.4/25.7 — resultado de `aplicar_proposta`.
    `motivo_rejeicao` preenchido apenas quando `proposta.status ==
    rejected` por falha de certificação."""

    proposta: WorkflowEvolutionProposal
    playbooks_certificados: list[PlaybookDefinition] = Field(default_factory=list)
    motivo_rejeicao: str | None = None


def aplicar_proposta(
    proposta: WorkflowEvolutionProposal,
    certificar: Callable[[PlaybookDefinition], PlaybookDefinition],
    grafo: KnowledgeGraph,
) -> ResultadoAplicacao:
    """Vol.VI Cap.25, secao 25.4/25.7 (AT-25.1) — nenhuma proposta atinge
    `applied` sem passar pela certificação COMPLETA de Playbook (Vol.V
    Cap.21). Se a certificação falhar, a proposta volta para `rejected`
    com o motivo anexado como evidência — nunca aplicada parcialmente.

    `certificar` é fornecido pelo chamador (tipicamente
    `workflow.playbooks.certificar_playbook` com os outros Playbooks ativos
    e os callables do Capability Registry já parametrizados via closure/
    `functools.partial`) — este módulo não acopla diretamente ao Runtime.

    `grafo` (Milestone 4 desta construção — achado de revisão): toda
    proposta que atinge `applied` registra os Playbooks certificados no
    Knowledge Graph (Vol.VI Cap.23) — nó `playbook` com aresta
    `justified-by` para a Human Review (Evidence First, AT-23.3) e
    `supersedes` para cada Playbook afetado pela proposta."""
    if proposta.reviewed_by is None:
        raise RevisaoHumanaObrigatoriaParaProposta(
            f"Proposta '{proposta.id}' nao pode ser aplicada sem Human Review, "
            "mesmo com evidencia operacional favoravel (secao 25.4, nota critica)"
        )
    if proposta.status != StatusProposta.APPROVED:
        raise PropostaNaoAprovada(
            f"Proposta '{proposta.id}' esta em status '{proposta.status.value}', "
            "so pode ser aplicada a partir de 'approved'"
        )

    try:
        certificados = [certificar(pb) for pb in proposta.proposed_change]
    except GapDeCertificacaoDoPlaybook as erro:
        proposta_rejeitada = proposta.model_copy(
            update={
                "status": StatusProposta.REJECTED,
                "evidence": proposta.evidence.model_copy(
                    update={
                        "metrics_snapshot": {
                            **proposta.evidence.metrics_snapshot,
                            "certification_failure": 1.0,
                        }
                    }
                ),
            }
        )
        return ResultadoAplicacao(proposta=proposta_rejeitada, motivo_rejeicao=str(erro))

    proposta_aplicada = proposta.model_copy(update={"status": StatusProposta.APPLIED})

    no_evidencia = KnowledgeNode(tipo=TipoNoKnowledge.EVIDENCE, ref=str(proposta.reviewed_by))
    grafo.adicionar_no(no_evidencia)
    for playbook in certificados:
        no_playbook = KnowledgeNode(tipo=TipoNoKnowledge.PLAYBOOK, ref=str(playbook.id))
        grafo.adicionar_no(no_playbook)
        grafo.adicionar_aresta(
            KnowledgeEdge(kind=TipoAresta.JUSTIFIED_BY, de=no_playbook, para=no_evidencia)
        )
        for afetado in proposta.affected_playbooks:
            no_afetado = KnowledgeNode(tipo=TipoNoKnowledge.PLAYBOOK, ref=str(afetado))
            grafo.adicionar_aresta(
                KnowledgeEdge(kind=TipoAresta.SUPERSEDES, de=no_playbook, para=no_afetado)
            )

    return ResultadoAplicacao(proposta=proposta_aplicada, playbooks_certificados=certificados)


def capacidades_com_recovery(playbook: PlaybookDefinition) -> set[CapabilityId]:
    """Vol.VI Cap.25, secao 25.5 (AT-25.2) — identidade estável entre
    Playbooks diferentes é a `CapabilityId`, nunca o índice em
    `steps_template` (que é local a cada Playbook)."""
    return {
        playbook.steps_template[indice].capability.capability_id
        for indice in playbook.recovery_defaults
        if indice < len(playbook.steps_template)
    }


class CoberturaDeRecoveryReduzida(Exception):
    """Vol.VI Cap.25, secao 25.5 (AT-25.2) — a fusão nunca reduz cobertura
    de recuperação em relação à união dos Playbooks originais."""


def verificar_cobertura_de_merge(
    originais: list[PlaybookDefinition], fundido: PlaybookDefinition
) -> None:
    """Vol.VI Cap.25, secao 25.5, item 2 (AT-25.2)."""
    esperado: set[CapabilityId] = set()
    for original in originais:
        esperado |= capacidades_com_recovery(original)

    faltando = esperado - capacidades_com_recovery(fundido)
    if faltando:
        raise CoberturaDeRecoveryReduzida(
            f"Fusao perde cobertura de recovery para Capabilities: {sorted(faltando)}"
        )


def depreciar_por_desuso(playbook: PlaybookDefinition) -> PlaybookDefinition:
    """Vol.VI Cap.25, secao 25.6 (AT-25.3) — nunca remove fisicamente;
    apenas move para `Deprecated`, preservando toda a definição original
    (auditável via Knowledge Graph, Cap.23, `provenance_trail`)."""
    return playbook.model_copy(update={"status": StatusPlaybook.DEPRECATED})


def deveria_propor_inversao_de_fallback(
    fallback_rate: float, limiar: float, execucoes_observadas: int, minimo_execucoes: int
) -> bool:
    """Vol.VI Cap.25, secao 25.2 (tabela, linha 1) — sinal de monitoramento
    contínuo; decide SE uma `WorkflowEvolutionProposal` deveria ser gerada,
    nunca aplica a inversão diretamente."""
    return execucoes_observadas >= minimo_execucoes and fallback_rate > limiar


def deveria_propor_depreciacao_por_desuso(
    dias_desde_ultimo_casamento: int, janela_dias: int = 180
) -> bool:
    """Vol.VI Cap.25, secao 25.6."""
    return dias_desde_ultimo_casamento >= janela_dias
