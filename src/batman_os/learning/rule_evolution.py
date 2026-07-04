"""Vol. VI, Cap. 24 — Rule Evolution.

Pipeline completo pelo qual um candidato a promoção — identificado pela
Operational Memory (Vol.III Cap.13, seção 13.6) — se torna uma regra ativa
consumida pelo Decision Engine (Vol.II Cap.8). Opera o Princípio 7 (Learn
Forever) e reduz Cognitive Debt ao longo do tempo.

ADR-0011: shadow mode obrigatório antes de qualquer regra assumir
autoridade decisória — Human Review sozinha não basta.

Fonte da verdade: docs/spec/06-learning/02-rule-evolution.md
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

from batman_os.foundation.types import (
    DecisionOption,
    HumanReviewRef,
    RecordId,
    RuleId,
    Timestamp,
    agora,
)
from batman_os.kernel.planning_engine import DecisionPoint


class StatusRegra(StrEnum):
    """Vol.VI Cap.24, secao 24.2 — mesmo ciclo de vida de Capability/Skill/
    Playbook: nunca remoção física, só desativação (secao 24.5)."""

    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    DISABLED = "disabled"


class DecisionPointSignature(BaseModel):
    """Vol.VI Cap.24, secao 24.2 — identifica a CLASSE de `DecisionPoint`
    que esta regra resolve. Modelo mínimo: casamento pela pergunta exata
    (a especificação não detalha a estrutura completa de assinatura)."""

    pergunta_padrao: str

    def casa_com(self, ponto: DecisionPoint) -> bool:
        return self.pergunta_padrao == ponto.pergunta


class RuleCondition(BaseModel):
    """Vol.VI Cap.24, secao 24.2 — expressão determinística sobre o
    contexto do `DecisionPoint`; mesmo padrão estrutural de `FieldCondition`
    (Vol.V Cap.21) — nunca semântica via LLM."""

    campo: str
    operador: Literal["eq", "in", "exists"]
    valor: Any = None

    def satisfeita_por(self, dados: dict[str, Any]) -> bool:
        if self.operador == "exists":
            return self.campo in dados
        if self.operador == "eq":
            return bool(dados.get(self.campo) == self.valor)
        return bool(dados.get(self.campo) in (self.valor or []))


class RulePromotion(BaseModel):
    """Vol.VI Cap.24, secao 24.2.

    Nota de implementação: `sourceCandidateId` da especificação referencia
    `PromotionCandidateId` (Vol.III Cap.13), mas `PromotionCandidate`
    (implementado em `runtime/operational_memory.py`) é identificado por
    `assinatura: str`, sem campo `id` próprio — usado aqui diretamente
    (gap mecânico, não decisão arquitetural nova).

    `reviewed_by` OBRIGATÓRIO (sem default) — é a própria estrutura do
    tipo, não uma checagem em runtime, que garante AT-24.2: nenhuma
    `RuleDefinition` pode existir sem `provenance.reviewedBy`."""

    source_candidate_signature: str
    supporting_records: list[RecordId] = Field(default_factory=list)
    reviewed_by: HumanReviewRef
    promoted_at: Timestamp = Field(default_factory=agora)


class RuleDefinition(BaseModel):
    """Vol.VI Cap.24, secao 24.2."""

    id: RuleId
    version: str
    applies_to: DecisionPointSignature
    condition: list[RuleCondition] = Field(default_factory=list)
    resolution: DecisionOption
    confidence_base: float
    provenance: RulePromotion
    status: StatusRegra = StatusRegra.DRAFT

    def especificidade(self) -> int:
        """Vol.VI Cap.24, secao 24.7 (AT-24.3) — 'especificidade da
        condição', mesmo critério de desempate de `IntentMatcher.
        especificidade()` (Vol.V Cap.21, secao 21.4)."""
        return len(self.condition)

    def casa_com(self, ponto: DecisionPoint, dados: dict[str, Any]) -> bool:
        if not self.applies_to.casa_com(ponto):
            return False
        return all(c.satisfeita_por(dados) for c in self.condition)


class RuleResolutionAmbiguity(Exception):
    """Vol.VI Cap.24, secao 24.7 (AT-24.3) — empate real de especificidade
    entre regras ativas para o mesmo `DecisionPointSignature` nunca é
    resolvido por escolha arbitrária."""

    def __init__(self, motivo: str, evidencia: dict[str, object] | None = None) -> None:
        super().__init__(motivo)
        self.evidencia = evidencia or {}


class ShadowEvaluation(BaseModel):
    """Vol.VI Cap.24, secao 24.4."""

    rule_id: RuleId
    decision_point_id: str
    shadow_resolution: DecisionOption
    actual_resolution: DecisionOption
    agreement: bool
    recorded_at: Timestamp = Field(default_factory=agora)


class ShadowModeInsuficiente(Exception):
    """Vol.VI Cap.24, secao 24.4 (AT-24.1, ADR-0011) — regra não pode
    atingir `active` sem shadow mode suficiente (volume e taxa de
    concordância), mesmo com Human Review já aprovada."""


def _partes_versao(versao: str) -> tuple[int, int, int]:
    major, minor, patch = (versao.split(".") + ["0", "0"])[:3]
    return int(major), int(minor), int(patch)


def resolve_rule(
    ponto: DecisionPoint, dados: dict[str, Any], candidatos: list[RuleDefinition]
) -> RuleDefinition | None:
    """Vol.VI Cap.24, secao 24.7 (AT-24.3) — análogo a `resolve_playbook`
    (Vol.V Cap.21, secao 21.4), mas sem `priority` explícita (a
    especificação de `RuleDefinition` não a inclui): especificidade da
    condição é o único critério antes do desempate por versão."""
    ativas = [r for r in candidatos if r.status == StatusRegra.ACTIVE]
    combinadas = [r for r in ativas if r.casa_com(ponto, dados)]
    if not combinadas:
        return None
    if len(combinadas) == 1:
        return combinadas[0]

    ordenadas = sorted(
        combinadas,
        key=lambda r: (-r.especificidade(), tuple(-p for p in _partes_versao(r.version))),
    )
    primeira, segunda = ordenadas[0], ordenadas[1]
    if primeira.especificidade() == segunda.especificidade():
        raise RuleResolutionAmbiguity(
            f"Empate real de especificidade entre regras '{primeira.id}' e '{segunda.id}' "
            "para o mesmo DecisionPointSignature",
            evidencia={"candidatas": [r.id for r in combinadas]},
        )
    return ordenadas[0]


def taxa_de_concordancia(avaliacoes: list[ShadowEvaluation]) -> float:
    if not avaliacoes:
        return 0.0
    concordantes = sum(1 for a in avaliacoes if a.agreement)
    return concordantes / len(avaliacoes)


def promover_a_active(
    regra: RuleDefinition,
    avaliacoes: list[ShadowEvaluation],
    taxa_minima: float,
    minimo_avaliacoes: int,
) -> RuleDefinition:
    """Vol.VI Cap.24, secao 24.3/24.4 (AT-24.1) — só promove a `active` com
    volume mínimo de avaliações de shadow mode E taxa de concordância acima
    do limiar; nunca confia apenas na Human Review isolada de dados
    empíricos subsequentes (ADR-0011)."""
    if len(avaliacoes) < minimo_avaliacoes:
        raise ShadowModeInsuficiente(
            f"Regra '{regra.id}': {len(avaliacoes)} avaliacoes de shadow mode, "
            f"minimo exigido {minimo_avaliacoes}"
        )

    taxa = taxa_de_concordancia(avaliacoes)
    if taxa < taxa_minima:
        raise ShadowModeInsuficiente(
            f"Regra '{regra.id}': taxa de concordancia {taxa:.2%} abaixo do "
            f"limiar {taxa_minima:.2%} ({len(avaliacoes)} avaliacoes)"
        )

    return regra.model_copy(update={"status": StatusRegra.ACTIVE})
