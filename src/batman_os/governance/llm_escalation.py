"""Vol. VII, Cap. 29 — LLM Escalation.

Consolida, sob a ótica de governança, toda a política de uso de LLM já
introduzida de forma dispersa ao longo da obra (ADR-0001, Volume I;
Decision Engine, Vol.II Cap.8; Execution Engine, Vol.III Cap.12) em uma
política única, auditável e versionada — a "constituição" que rege
quando, como e com que limites o Batman pode consultar um LLM.

Fonte da verdade: docs/spec/07-governance/03-llm-escalation.md
"""

from __future__ import annotations

from typing import Literal, NewType

from pydantic import BaseModel, Field

from batman_os.foundation.types import DateRange, HumanReviewRef, MissionTypeId
from batman_os.kernel.decision_engine import Decision

PolicyId = NewType("PolicyId", str)

RequerAprovacaoHumana = Literal["always", "irreversible-only", "never"]
NivelDeValidacaoDeSaida = Literal["schema-only", "schema-plus-domain-invariants"]

# Vol.VII Cap.29, secao 29.2/29.6 — ordem de restritividade de
# `requiresHumanCoApproval`, do mais restritivo ao menos restritivo.
# Usada por `relaxa_controle()` (AT-29.2): qualquer mudanca que DIMINUA
# este valor exige rationale com evidencia quantitativa.
_RESTRITIVIDADE: dict[RequerAprovacaoHumana, int] = {
    "always": 2,
    "irreversible-only": 1,
    "never": 0,
}


class RatePolicy(BaseModel):
    """Vol.VII Cap.29, secao 29.2 — mesmo formato do circuit breaker por
    Tool (Vol.IV Cap.18): limiar de taxa sobre uma janela de tentativas."""

    taxa_maxima: float
    tamanho_janela: int


class LLMEscalationPolicy(BaseModel):
    """Vol.VII Cap.29, secao 29.2.

    Nota crítica de auto-referência (secao 29.2): a própria política passa
    por Human Review antes de `active` — `status`/`approved_by` seguem o
    mesmo padrão de certificação já usado em Capability/Playbook/Rule."""

    id: PolicyId
    version: str
    scope: Literal["global"] | list[MissionTypeId]
    max_retries_per_decision_point: int
    circuit_breaker_threshold: RatePolicy
    requires_human_co_approval: RequerAprovacaoHumana
    output_validation_level: NivelDeValidacaoDeSaida
    status: Literal["draft", "active"] = "draft"
    approved_by: HumanReviewRef | None = None


class PoliticaSemAprovacao(Exception):
    """Vol.VII Cap.29, secao 29.7 (AT-29.1) — nenhuma `LLMEscalationPolicy`
    atinge `active` sem `approvedBy` preenchido."""


def ativar_politica(policy: LLMEscalationPolicy) -> LLMEscalationPolicy:
    """Vol.VII Cap.29, secao 29.2 (AT-29.1)."""
    if policy.approved_by is None:
        raise PoliticaSemAprovacao(
            f"LLMEscalationPolicy '{policy.id}' nao pode ser ativada sem approvedBy "
            "(secao 29.2, nota critica de auto-referencia)"
        )
    return policy.model_copy(update={"status": "active"})


def relaxa_controle(anterior: RequerAprovacaoHumana, nova: RequerAprovacaoHumana) -> bool:
    """Vol.VII Cap.29, secao 29.6 (AT-29.2) — verdadeiro quando `nova` é
    menos restritiva que `anterior` (ex.: `always` -> `irreversible-only`)."""
    return _RESTRITIVIDADE[nova] < _RESTRITIVIDADE[anterior]


class RelaxamentoDeControleSemEvidencia(Exception):
    """Vol.VII Cap.29, secao 29.6/29.7 (AT-29.2) — mudança que relaxa
    `requiresHumanCoApproval` exige `rationale` com evidência quantitativa
    (extraída de `LLMUsageAudit`), nunca apenas conveniência."""


def validar_mudanca_de_politica(
    anterior: LLMEscalationPolicy,
    nova: LLMEscalationPolicy,
    rationale: str,
    evidencia_quantitativa: dict[str, float] | None,
) -> None:
    """Vol.VII Cap.29, secao 29.6 (AT-29.2) — só impõe a exigência de
    evidência quando a mudança de fato relaxa o controle; apertar um
    controle (ou mantê-lo) segue apenas o processo normal de Human Review
    (Cap.28), sem essa checagem extra."""
    if not relaxa_controle(anterior.requires_human_co_approval, nova.requires_human_co_approval):
        return

    if not rationale.strip():
        raise RelaxamentoDeControleSemEvidencia(
            f"Mudanca de '{anterior.requires_human_co_approval}' para "
            f"'{nova.requires_human_co_approval}' relaxa o controle e exige rationale "
            "com evidencia quantitativa, nunca so conveniencia (secao 29.6)"
        )
    if not evidencia_quantitativa:
        raise RelaxamentoDeControleSemEvidencia(
            f"Mudanca de '{anterior.requires_human_co_approval}' para "
            f"'{nova.requires_human_co_approval}' exige evidencia quantitativa extraida "
            "de LLMUsageAudit (AT-29.2), nao apenas rationale textual"
        )


class LLMUsageSummary(BaseModel):
    """Vol.VII Cap.29, secao 29.5 — resumo por `MissionTypeId`."""

    total_decision_points: int
    resolved_by_llm: int


class LLMUsageAudit(BaseModel):
    """Vol.VII Cap.29, secao 29.5 — relatório agregado consumido pelo
    Observability Engine (Cap.30); insumo direto de Cognitive Debt
    (Vol.I Cap.4)."""

    period: DateRange
    total_decision_points: int
    resolved_by_llm: int
    rejected_by_validation: int = 0
    circuit_breaker_trips: int = 0
    by_mission_type: dict[MissionTypeId, LLMUsageSummary] = Field(default_factory=dict)

    @property
    def resolved_by_llm_percentage(self) -> float:
        if self.total_decision_points == 0:
            return 0.0
        return self.resolved_by_llm / self.total_decision_points


def calcular_llm_usage_audit(
    decisions: list[Decision],
    periodo: DateRange,
    rejected_by_validation: int = 0,
    circuit_breaker_trips: int = 0,
) -> LLMUsageAudit:
    """Vol.VII Cap.29, secao 29.5 (AT-29.3) — função PURA e determinística:
    a mesma lista de `Decision`s no mesmo período sempre produz o mesmo
    relatório — é essa reprodutibilidade que garante que a auditoria seja
    reconciliável (recalculável a partir da mesma fonte de verdade, nunca
    uma métrica isolada e divergente).

    `rejected_by_validation`/`circuit_breaker_trips` fornecidos pelo
    chamador: o Decision Engine (Vol.II Cap.8) hoje não expõe contadores
    próprios para essas duas métricas (só `taxa_llm()`, tentativas bem-
    sucedidas) — gap de instrumentação documentado, não uma omissão
    silenciosa desta função."""
    no_periodo = [d for d in decisions if periodo.inicio <= d.resolved_at <= periodo.fim]
    resolvidas_por_llm = sum(1 for d in no_periodo if d.resolved_by == "llm")

    return LLMUsageAudit(
        period=periodo,
        total_decision_points=len(no_periodo),
        resolved_by_llm=resolvidas_por_llm,
        rejected_by_validation=rejected_by_validation,
        circuit_breaker_trips=circuit_breaker_trips,
    )
