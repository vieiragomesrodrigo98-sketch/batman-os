"""Vol. VI, Cap. 26 — Operational Learning.

Fecha o Volume VI. Secao 26.3: Operational Learning NÃO é um componente
novo de software — é o NOME do ciclo que amarra Operational Memory
(Vol.III Cap.13), Rule Evolution (Cap.24), Workflow Evolution (Cap.25) e
Knowledge Graph (Cap.23). Este módulo, portanto, não define um "motor"
próprio — apenas as funções de medição/consulta que tornam o ciclo
mensurável como uma coisa só (Cognitive Debt por MissionTypeId, saúde do
backlog de Human Review), consistente com a secao 26.3.

Fonte da verdade: docs/spec/06-learning/04-operational-learning.md
"""

from __future__ import annotations

from datetime import timedelta

from pydantic import BaseModel

from batman_os.foundation.types import HumanReviewRef, MissionTypeId, Timestamp
from batman_os.kernel.mission_runtime import CognitiveDebtFlag
from batman_os.learning.rule_evolution import RuleDefinition
from batman_os.runtime.operational_memory import OperationalRecord


class PontoCognitiveDebt(BaseModel):
    """Vol.VI Cap.26, secao 26.4 — um ponto da trajetória de Cognitive Debt
    de um `MissionTypeId` em uma janela de tempo."""

    periodo_inicio: Timestamp
    periodo_fim: Timestamp
    total_missoes: int
    proporcao_autonoma: float


def cognitive_debt_por_tipo(
    registros: list[OperationalRecord], mission_type: MissionTypeId
) -> float:
    """Vol.VI Cap.26, secao 26.4 (AT-26.1) — Cognitive Debt (Vol.I Cap.4,
    secao 4.9.1) isolado por `MissionTypeId`, nunca apenas agregado
    globalmente — é o que permite distinguir estagnação legítima de um
    domínio maduro de um gargalo real de governança (secao 26.4, nota
    crítica). Retorna a proporção NÃO autônoma (0.0 = toda missão
    autônoma; 1.0 = nenhuma)."""
    relevantes = [r for r in registros if r.mission_type == mission_type]
    if not relevantes:
        return 0.0
    nao_autonomos = sum(
        1 for r in relevantes if r.cognitive_debt_flag != CognitiveDebtFlag.AUTONOMOUS
    )
    return nao_autonomos / len(relevantes)


def trajetoria_cognitive_debt(
    registros: list[OperationalRecord],
    mission_type: MissionTypeId,
    tamanho_janela: timedelta,
) -> list[PontoCognitiveDebt]:
    """Vol.VI Cap.26, secao 26.4 (AT-26.1) — divide o histórico de um
    `MissionTypeId` em janelas de tempo sequenciais, cada uma com sua
    própria proporção de Cognitive Debt, para tornar visível a TRAJETÓRIA
    (queda esperada ao longo do tempo, secao 26.4), não só um número
    agregado congelado."""
    relevantes = sorted(
        (r for r in registros if r.mission_type == mission_type), key=lambda r: r.recorded_at
    )
    if not relevantes:
        return []

    pontos: list[PontoCognitiveDebt] = []
    inicio_janela = relevantes[0].recorded_at
    fim_ultimo = relevantes[-1].recorded_at
    while inicio_janela <= fim_ultimo:
        fim_janela = inicio_janela + tamanho_janela
        na_janela = [r for r in relevantes if inicio_janela <= r.recorded_at < fim_janela]
        if na_janela:
            nao_autonomos = sum(
                1 for r in na_janela if r.cognitive_debt_flag != CognitiveDebtFlag.AUTONOMOUS
            )
            pontos.append(
                PontoCognitiveDebt(
                    periodo_inicio=inicio_janela,
                    periodo_fim=fim_janela,
                    total_missoes=len(na_janela),
                    proporcao_autonoma=1.0 - (nao_autonomos / len(na_janela)),
                )
            )
        inicio_janela = fim_janela
    return pontos


def rastrear_origem_da_regra(regra: RuleDefinition) -> HumanReviewRef:
    """Vol.VI Cap.26, secao 26.7 (AT-26.2) — toda mudança de comportamento
    do Decision Engine atribuível a uma regra é sempre rastreável até uma
    `RuleDefinition` com `provenance.reviewedBy` preenchido. A garantia é
    ESTRUTURAL (`RulePromotion.reviewed_by` é campo obrigatório sem
    default, Cap.24, AT-24.2) — esta função apenas formaliza o ponto de
    consulta para auditoria de ponta a ponta do ciclo completo."""
    return regra.provenance.reviewed_by


class ItemDeBacklog(BaseModel):
    """Vol.VI Cap.26, secao 26.6/26.7 (AT-26.3) — um candidato a promoção
    (Vol.III Cap.13) ou uma `WorkflowEvolutionProposal` (Cap.25) do ponto
    de vista do backlog de Human Review: quando foi identificado, quando
    (se já) foi resolvido."""

    identificado_em: Timestamp
    resolvido_em: Timestamp | None = None


def idade_do_backlog_pendente(itens: list[ItemDeBacklog], agora_: Timestamp) -> list[timedelta]:
    """Vol.VI Cap.26, secao 26.6 (AT-26.3) — idade de cada item AINDA
    pendente; backlog crescendo sem parar sinaliza gargalo estrutural de
    Human Review (secao 26.6), nunca resolvido afrouxando a exigência de
    revisão humana."""
    return [agora_ - item.identificado_em for item in itens if item.resolvido_em is None]


def tempo_de_resolucao_dos_concluidos(itens: list[ItemDeBacklog]) -> list[timedelta]:
    """Vol.VI Cap.26, secao 26.7 (AT-26.3) — tempo entre identificação e
    resolução de cada item já concluído (aprovado, aplicado ou arquivado)."""
    return [
        item.resolvido_em - item.identificado_em for item in itens if item.resolvido_em is not None
    ]
