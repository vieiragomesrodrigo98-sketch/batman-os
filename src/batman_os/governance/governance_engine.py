"""Vol. VII, Cap. 27 — Governance Engine.

Consolida, expõe e alarma sobre a saúde de conformidade do Batman OS em
relação aos seus próprios princípios (Volume I) — sem executar nenhuma
ação do Kernel diretamente (ADR-0012). A mesma relação que a Operational
Memory (ADR-0004) tem com o comportamento do Kernel: informa e aciona,
nunca decide sozinho por substituição.

ADR-0012: Governance Engine sem autoridade executiva direta — este módulo
NUNCA importa de `batman_os.kernel` (AT-27.3).

Fonte da verdade: docs/spec/07-governance/01-governance-engine.md
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from batman_os.foundation.types import (
    AlertId,
    Evidence,
    HumanReviewRef,
    MissionId,
    TenantId,
    Timestamp,
    agora,
    novo_uuid7,
)


class FonteAlerta(StrEnum):
    """Vol.VII Cap.27, secao 27.4 — `GovernanceAlert.source`."""

    SLA_BREACH = "sla-breach"
    LLM_CIRCUIT_BREAKER = "llm-circuit-breaker"
    TENANT_ISOLATION_INCIDENT = "tenant-isolation-incident"
    HUMAN_REVIEW_BACKLOG = "human-review-backlog"
    RULE_DRIFT = "rule-drift"
    ADDENDUM_REVIEW_REQUEST = "addendum-review-request"


class SeveridadeAlerta(StrEnum):
    """Vol.VII Cap.27, secao 27.4."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class StatusAlerta(StrEnum):
    """Vol.VII Cap.27, secao 27.4."""

    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class GovernanceAlert(BaseModel):
    """Vol.VII Cap.27, secao 27.4."""

    id: AlertId = Field(default_factory=lambda: AlertId(novo_uuid7()))
    source: FonteAlerta
    severity: SeveridadeAlerta
    evidence: list[Evidence]
    related_mission_id: MissionId | None = None
    related_tenant_id: TenantId | None = None
    status: StatusAlerta = StatusAlerta.OPEN
    created_at: Timestamp = Field(default_factory=agora)
    acknowledged_by: HumanReviewRef | None = None
    resolution: str | None = None


class EvidenciaObrigatoriaParaAlerta(Exception):
    """Vol.VII Cap.27, secao 27.9 (AT-27.1) — nenhum `GovernanceAlert` pode
    ser criado sem `evidence` associada (Evidence First)."""


class AlertaDesconhecido(Exception):
    """`acknowledge`/`resolve` chamado com um `AlertId` não registrado."""


class GovernanceEngine:
    """Vol.VII Cap.27, secao 27.4 — só consome eventos/registros de outros
    componentes (Event Bus, Operational Memory, Knowledge Graph); nunca
    publica algo que o Kernel consome de volta (secao 27.5)."""

    def __init__(self) -> None:
        self._alertas: dict[AlertId, GovernanceAlert] = {}

    def raise_alert(self, alert: GovernanceAlert) -> None:
        """AT-27.1."""
        if not alert.evidence:
            raise EvidenciaObrigatoriaParaAlerta(
                f"GovernanceAlert (source='{alert.source.value}') nao pode ser "
                "levantado sem evidence (Evidence First)"
            )
        self._alertas[alert.id] = alert

    def get_open_alerts(
        self,
        source: FonteAlerta | None = None,
        severity: SeveridadeAlerta | None = None,
    ) -> list[GovernanceAlert]:
        return [
            a
            for a in self._alertas.values()
            if a.status == StatusAlerta.OPEN
            and (source is None or a.source == source)
            and (severity is None or a.severity == severity)
        ]

    def acknowledge(self, alert_id: AlertId, by: HumanReviewRef) -> GovernanceAlert:
        alerta = self._exigir(alert_id)
        atualizado = alerta.model_copy(
            update={"status": StatusAlerta.ACKNOWLEDGED, "acknowledged_by": by}
        )
        self._alertas[alert_id] = atualizado
        return atualizado

    def resolve(self, alert_id: AlertId, resolution: str) -> GovernanceAlert:
        alerta = self._exigir(alert_id)
        atualizado = alerta.model_copy(
            update={"status": StatusAlerta.RESOLVED, "resolution": resolution}
        )
        self._alertas[alert_id] = atualizado
        return atualizado

    def _exigir(self, alert_id: AlertId) -> GovernanceAlert:
        if alert_id not in self._alertas:
            raise AlertaDesconhecido(f"GovernanceAlert desconhecido: {alert_id}")
        return self._alertas[alert_id]


class StatusAnexo(StrEnum):
    """Vol.VII Cap.27, secao 27.6 — ciclo de vida de um Anexo (`ADDENDA.md`)."""

    PROPOSED = "proposed"
    UNDER_REVIEW = "under-review"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class AddendumRecord(BaseModel):
    """Vol.VII Cap.27, secao 27.6 — registro mínimo de um Anexo do ponto de
    vista do Governance Engine; o conteúdo do Anexo em si continua vivendo
    em `ADDENDA.md` (fora do escopo de código desta construção)."""

    add_id: str
    status: StatusAnexo = StatusAnexo.PROPOSED
    reviewed_by: HumanReviewRef | None = None


class RevisaoHumanaObrigatoriaParaAnexo(Exception):
    """Vol.VII Cap.27, secao 27.6 (AT-27.2) — nenhum Anexo transiciona para
    `Accepted` sem `HumanReviewRef` registrado, nem mesmo quando o revisor
    humano é o próprio autor da obra atuando nesse papel (secao 27.6)."""


def aceitar_anexo(anexo: AddendumRecord, reviewed_by: HumanReviewRef | None) -> AddendumRecord:
    """Vol.VII Cap.27, secao 27.6 (AT-27.2)."""
    if reviewed_by is None:
        raise RevisaoHumanaObrigatoriaParaAnexo(
            f"Anexo '{anexo.add_id}' nao pode transicionar para Accepted sem "
            "HumanReviewRef registrado"
        )
    return anexo.model_copy(update={"status": StatusAnexo.ACCEPTED, "reviewed_by": reviewed_by})
