"""Vol. I, Cap. 4 — vocabulario oficial do Kernel: IDs e tipos compartilhados.

Fonte da verdade: docs/spec/01-foundation/04-terminology.md

Regra do Cap.4 (nao negociavel): estes termos nao podem ser usados com outro
sentido em nenhum outro modulo. Nomenclatura do Batman atual (agente, ledger,
sweep, patrol, Alfred, Robin, IDs de regra) e preservada ao redor deste nucleo,
nunca substituindo-o — ver README.md, secao "Convencao de nomenclatura".
"""

from __future__ import annotations

import secrets
import time
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import NewType

from pydantic import BaseModel, Field

Timestamp = datetime


def agora() -> Timestamp:
    """Instante atual em UTC — default de todo campo Timestamp do Kernel."""
    return datetime.now(UTC)


def novo_uuid7() -> str:
    """UUID v7 (ordenavel por tempo de criacao) — exigido pelo campo `id` de
    Mission (Vol.II Cap.6, secao 6.2: "UUID v7 — ordenavel por tempo de criacao")."""
    ts_ms = time.time_ns() // 1_000_000
    rand_a = secrets.randbits(12)
    rand_b = secrets.randbits(62)
    high = ((ts_ms & 0xFFFFFFFFFFFF) << 16) | (0x7 << 12) | rand_a
    low = (0b10 << 62) | rand_b
    return str(uuid.UUID(int=(high << 64) | low))


def novo_ulid_like() -> str:
    """Identificador ordenavel para EventId (Vol.II Cap.10 pede ULID). Reaproveita
    o gerador de UUID7 — tambem ordenavel por tempo — ate uma biblioteca de ULID
    real ser adotada (Volume VIII, Infrastructure, ainda nao escrito)."""
    return novo_uuid7()


# IDs — NewType sobre str para o mypy impedir troca acidental entre eles
# (ex.: passar um CapabilityId onde se espera um SkillId nao deve compilar).
MissionId = NewType("MissionId", str)
MissionTypeId = NewType("MissionTypeId", str)
PlanId = NewType("PlanId", str)
StepId = NewType("StepId", str)
DecisionId = NewType("DecisionId", str)
DecisionPointId = NewType("DecisionPointId", str)
EventId = NewType("EventId", str)
WorkflowRunId = NewType("WorkflowRunId", str)
CapabilityId = NewType("CapabilityId", str)
SkillId = NewType("SkillId", str)
ToolId = NewType("ToolId", str)
OperatorId = NewType("OperatorId", str)
PlaybookId = NewType("PlaybookId", str)
TenantId = NewType("TenantId", str)
RuleId = NewType("RuleId", str)
AdrId = NewType("AdrId", str)
EvidenceId = NewType("EvidenceId", str)
RecordId = NewType("RecordId", str)  # OperationalRecord (Vol.III Cap.13)


class KnowledgeAssetKind(StrEnum):
    """Vol.I Cap.4, secao 4.7 — tipos de Knowledge Asset (guarda-chuva do
    Principio 7, Learn Forever)."""

    REGRA = "regra"
    TESTE = "teste"
    WORKFLOW = "workflow"
    CAPABILITY = "capability"
    SKILL = "skill"
    EVIDENCIA = "evidencia"
    ADR = "adr"
    PLAYBOOK = "playbook"


class KnowledgeAssetRef(BaseModel):
    """Referencia opaca a um Knowledge Asset — usada por `Mission.
    knowledge_assets_produced` (Vol.II Cap.6) e pelo Knowledge Graph
    (Vol.VI Cap.23, `KnowledgeNode`)."""

    tipo: KnowledgeAssetKind
    ref_id: str


class Evidence(BaseModel):
    """Vol.I Cap.3, secao 3.4 — Principio 3 (Evidence First). Toda Decision
    (Vol.II Cap.8) carrega evidencia rastreavel; nunca pode existir uma decisao
    com evidencia vazia (AT-8.1)."""

    origem: str
    evidencias: list[str] = Field(default_factory=list)
    confianca: float | None = None
    historico: list[str] = Field(default_factory=list)


class Reversibilidade(StrEnum):
    """Vol.II Cap.8, secao 8.3 — `EscalationPolicy.reversibility`. Decisoes
    irreversiveis nunca vao direto a LLM sem escalonamento humano intermediario
    (AT-8.3)."""

    REVERSIVEL = "reversible"
    IRREVERSIVEL = "irreversible"
