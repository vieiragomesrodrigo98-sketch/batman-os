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
from typing import Any, Literal, NewType

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
HumanReviewRef = NewType("HumanReviewRef", str)  # Vol.VII Cap.28, referenciado desde Vol.V Cap.21
ProposalId = NewType("ProposalId", str)  # Vol.VI Cap.25 (WorkflowEvolutionProposal)
AlertId = NewType("AlertId", str)  # Vol.VII Cap.27 (GovernanceAlert)


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


class Criticidade(StrEnum):
    """Vol.V Cap.20, secao 20.2/20.3 — `MissionTypeDefinition.criticality`.
    Referenciada de forma cruzada pelo Decision Engine (Vol.II Cap.8, secao
    20.3: `critical` nunca escala a LLM sem humano intermediario) e pelo
    Scheduler (Vol.II Cap.10: prioridade base) antes do Volume V ter seu
    proprio modulo — colocada aqui pelo mesmo motivo dos demais tipos desta
    secao (evitar import circular kernel <-> workflow, Vol.VIII Cap.32
    secao 32.3: `workflow` depende de `kernel`, nunca o contrario)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Reversibilidade(StrEnum):
    """Vol.II Cap.8, secao 8.3 — `EscalationPolicy.reversibility`. Decisoes
    irreversiveis nunca vao direto a LLM sem escalonamento humano intermediario
    (AT-8.3)."""

    REVERSIVEL = "reversible"
    IRREVERSIVEL = "irreversible"


# Os tipos abaixo (CapabilityRef, DecisionOption, EscalationPolicy,
# RecoveryStrategy) sao definidos formalmente em capitulos posteriores
# (Vol.III Cap.11, Vol.II Cap.8, Vol.II Cap.9) mas sao referenciados de forma
# cruzada por Cap.7 (Planning Engine) e Cap.8/9 antes de cada um ter seu
# proprio modulo. Colocados aqui, na Foundation, especificamente para evitar
# import circular entre kernel/planning_engine.py, kernel/decision_engine.py
# e kernel/workflow_engine.py — nao e uma reinterpretacao do glossario do
# Cap.4, e sim uma escolha de organizacao de modulos.


class CapabilityRef(BaseModel):
    """Vol.II Cap.7 (`PlanStep.capability`) / Vol.III Cap.11, secao 11.3.1 —
    um `ExecutionPlan` ja gerado referencia uma versao especifica de
    Capability, nunca "a mais recente" implicitamente (regra de ouro do
    capitulo, o que garante `planHash` estavel mesmo se o catalogo evoluir)."""

    capability_id: CapabilityId
    versao: str


class DecisionOption(BaseModel):
    """Vol.II Cap.7 (`DecisionPoint.options`) / Cap.8 (`Decision.chosenOption`)
    — uma alternativa concreta que um DecisionPoint pode resolver."""

    id: str
    descricao: str
    payload: dict[str, Any] = Field(default_factory=dict)


class EscalationPolicy(BaseModel):
    """Vol.II Cap.8, secao 8.3 — configuravel por tipo de missao/decisao,
    nunca hardcoded no Kernel."""

    confidence_threshold: float
    preferred_escalation: Literal["human", "llm"]
    max_llm_retries: int
    reversibility: Reversibilidade


class TipoRecoveryStrategy(StrEnum):
    """Vol.II Cap.9, secao 9.5; `FALLBACK_CAPABILITY` adicionado no Vol.V
    Cap.22, secao 22.2 (estende, nunca substitui, o conjunto original)."""

    RETRY = "retry"
    COMPENSATE = "compensate"
    SKIP_IF_OPTIONAL = "skip-if-optional"
    ESCALATE = "escalate"
    FALLBACK_CAPABILITY = "fallback-capability"


class ImpactoDegradacao(StrEnum):
    """Vol.V Cap.22, secao 22.4 — `DegradationRecord.impact`."""

    COSMETIC = "cosmetic"
    REDUCED_FUNCTIONALITY = "reduced-functionality"
    REQUIRES_FOLLOW_UP = "requires-follow-up"


class OperatorRef(BaseModel):
    """Vol.III Cap.12 (`ExecutionEngine.invoke`) / Vol.IV Cap.15 — referencia
    opaca a um Operador. Colocada aqui pelo mesmo motivo dos demais tipos
    desta secao: Cap.12 (Runtime) precisa dela antes de Cap.15 (Capabilities)
    ter seu proprio modulo."""

    operator_id: OperatorId


class SkillRef(BaseModel):
    """Vol.III Cap.11 (`CapabilityDefinition.requiredSkills`) / Vol.IV Cap.17
    — referencia a uma Skill que uma Capability usa internamente. Colocada
    aqui pelo mesmo motivo dos demais tipos desta secao: Cap.11 (Runtime) e
    Cap.17 (Capabilities) se referenciam mutuamente."""

    skill_id: SkillId


class RecoveryStrategy(BaseModel):
    """Vol.II Cap.9, secao 9.5 — uniao discriminada por `tipo`, representada
    aqui como um unico modelo com campos opcionais por variante (mais simples
    de validar em Pydantic que uma uniao discriminada completa). Campos
    irrelevantes ao `tipo` corrente ficam `None`."""

    tipo: TipoRecoveryStrategy
    max_tentativas: int | None = None  # retry
    backoff: Literal["fixed", "exponential"] | None = None  # retry
    compensation_step_id: StepId | None = None  # compensate
    alternative_capability: CapabilityRef | None = None  # fallback-capability (Vol.V Cap.22)
    escalation_policy: EscalationPolicy | None = None  # escalate


class DegradationRecord(BaseModel):
    """Vol.V Cap.22, secao 22.4 — referenciada por `Mission` (Vol.II Cap.6)
    antes do Volume V ter modulo proprio; mesmo motivo de `Criticidade`
    (evitar import circular kernel <-> workflow, Vol.VIII Cap.32 secao 32.3)."""

    step_id: StepId
    exhausted_chain: list[RecoveryStrategy] = Field(default_factory=list)
    impact: ImpactoDegradacao
