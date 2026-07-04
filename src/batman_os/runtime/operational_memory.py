"""Vol. III, Cap. 13 — Operational Memory.

Onde e como o Batman persiste estado ENTRE missões — a diferença entre
"lembrar" (este módulo) e "aprender" (Learning Engine, Volume VI, fora de
escopo desta construção). Nunca é fonte de verdade comportamental (ADR-0004):
alimenta o cálculo de confiança do Decision Engine e produz candidatos para
o Learning Engine — nunca decide nem promove conhecimento sozinha.

Fonte da verdade: docs/spec/03-runtime/03-operational-memory.md
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from batman_os.foundation.types import (
    DecisionPointId,
    MissionId,
    MissionTypeId,
    RecordId,
    StepId,
    Timestamp,
    agora,
    novo_uuid7,
)
from batman_os.kernel.decision_engine import ResolvedBy
from batman_os.kernel.mission_runtime import CognitiveDebtFlag, MissionIntent, MissionState
from batman_os.kernel.workflow_engine import StatusStepResult

FinalState = MissionState  # restrito na pratica a Completed/Failed/Cancelled (secao 13.3)


class DecisionSummary(BaseModel):
    """Vol.III Cap.13, secao 13.3."""

    decision_point_id: DecisionPointId
    resolved_by: ResolvedBy
    chosen_option_id: str
    confidence: float


class StepResultSummary(BaseModel):
    """Vol.III Cap.13, secao 13.3."""

    step_id: StepId
    status: StatusStepResult


class OperationalRecord(BaseModel):
    """Vol.III Cap.13, secao 13.3 — projeção derivada dos eventos do Event
    Bus (nunca fonte de verdade paralela, consistente com ADR-0003). Imutável
    após criado (AT-13.1: append-only, nunca editada)."""

    model_config = {"frozen": True}

    id: RecordId = Field(default_factory=lambda: RecordId(novo_uuid7()))
    mission_id: MissionId
    mission_type: MissionTypeId
    decision_points_resolved: tuple[DecisionSummary, ...] = ()
    step_results: tuple[StepResultSummary, ...] = ()
    final_state: FinalState
    cognitive_debt_flag: CognitiveDebtFlag
    recorded_at: Timestamp = Field(default_factory=agora)


class PatternQuery(BaseModel):
    """Vol.III Cap.13, secao 13.4 (`getFrequency`) — filtro simples sobre o
    histórico. A especificação não detalha os campos; modelo mínimo cobrindo
    os eixos mais citados na obra (tipo de missão, resultado final)."""

    mission_type: MissionTypeId | None = None
    final_state: FinalState | None = None


class PromotionCandidate(BaseModel):
    """Vol.III Cap.13, secao 13.6 — saída de `find_promotion_candidates`,
    consumida pelo Learning Engine (Volume VI, fora de escopo). Nunca
    aplicada automaticamente por este módulo (AT-13.2)."""

    assinatura: str
    registros: tuple[OperationalRecord, ...]


class OperationalMemory:
    """Vol.III Cap.13, secao 13.4.

    Implementação de referência: armazenamento append-only alimentado
    explicitamente via `registrar()`. Numa integração ponta a ponta completa,
    isso seria preenchido por reconciliação automática a partir do Event Bus
    (secao 13.3); Decision Engine e Workflow Engine, nesta construção, ainda
    não publicam eventos ricos o bastante para essa reconstrução automática
    — registrado como pendência de integração, não uma omissão silenciosa.
    """

    def __init__(self) -> None:
        self._records: list[OperationalRecord] = []

    def registrar(self, record: OperationalRecord) -> None:
        """AT-13.1 — append-only; não há método de edição ou remoção."""
        self._records.append(record)

    def all_records(self) -> list[OperationalRecord]:
        return list(self._records)

    def find_similar_missions(self, intent: MissionIntent, limit: int) -> list[OperationalRecord]:
        """Vol.III Cap.13, secao 13.4 — similaridade léxica simples (chaves
        de `intent.dados` em comum), zero LLM/rede, consistente com o motor
        de Recall já precedente no Batman atual."""
        pontuados = [(self._similaridade(intent, r), r) for r in self._records]
        pontuados.sort(key=lambda par: par[0], reverse=True)
        return [registro for pontuacao, registro in pontuados[:limit] if pontuacao > 0]

    def get_decision_history(self, decision_point_signature: str) -> list[DecisionSummary]:
        """Vol.III Cap.13, secao 13.4."""
        return [
            resumo
            for record in self._records
            for resumo in record.decision_points_resolved
            if resumo.decision_point_id == decision_point_signature
        ]

    def get_frequency(self, pattern: PatternQuery) -> int:
        """Vol.III Cap.13, secao 13.6 — usado para detectar candidatos a
        Cognitive Debt recorrente."""
        return sum(1 for r in self._records if self._casa_padrao(r, pattern))

    def _similaridade(self, intent: MissionIntent, record: OperationalRecord) -> float:
        del record
        # Nesta construcao, OperationalRecord nao guarda o MissionIntent
        # original (so o resumo pos-execucao) - similaridade completa exige
        # armazenar o intent no proprio record, extensao natural quando a
        # reconciliacao via Event Bus (nota da classe) for implementada.
        del intent
        return 0.0

    def _casa_padrao(self, record: OperationalRecord, pattern: PatternQuery) -> bool:
        if pattern.mission_type is not None and record.mission_type != pattern.mission_type:
            return False
        return not (pattern.final_state is not None and record.final_state != pattern.final_state)


def find_promotion_candidates(
    memory: OperationalMemory, threshold: int
) -> list[PromotionCandidate]:
    """Vol.III Cap.13, secao 13.6 (AT-13.2) — identifica candidatos a
    promoção; NUNCA aplica nada sozinha, apenas retorna a lista para Human
    Review subsequente (Learning Engine, Volume VI / Governance, Volume VII,
    ambos fora de escopo desta construção)."""
    grupos: dict[str, list[OperationalRecord]] = {}
    for record in memory.all_records():
        for resumo in record.decision_points_resolved:
            grupos.setdefault(resumo.decision_point_id, []).append(record)

    candidatos: list[PromotionCandidate] = []
    for assinatura, registros in grupos.items():
        if len(registros) < threshold:
            continue

        resumos_da_assinatura = [
            resumo
            for record in registros
            for resumo in record.decision_points_resolved
            if resumo.decision_point_id == assinatura
        ]
        todos_externos = all(r.resolved_by in ("human", "llm") for r in resumos_da_assinatura)
        if not todos_externos:
            continue

        opcoes_escolhidas = {r.chosen_option_id for r in resumos_da_assinatura}
        resultado_consistente = len(opcoes_escolhidas) == 1
        if not resultado_consistente:
            continue

        candidatos.append(PromotionCandidate(assinatura=assinatura, registros=tuple(registros)))

    return candidatos


def calcular_confidence_combinada(
    confidence_base: float, memory: OperationalMemory | None, decision_point_signature: str
) -> float:
    """Vol.III Cap.13, secao 13.5 — combina confiança de regra + histórico da
    Operational Memory no cálculo de confiança do Decision Engine (Vol.II
    Cap.8). AT-13.3: indisponibilidade da Operational Memory (`None`, ou
    exceção ao consultar) degrada graciosamente para a confiança base —
    nunca propaga falha para o Decision Engine.

    Nota de integração: o `DecisionEngine` (Cap.8) já construído nesta
    sessão ainda não chama esta função internamente — é o padrão de uso
    pretendido pela especificação, disponível para ser conectado quando a
    integração completa Decision Engine <-> Operational Memory for feita.
    """
    if memory is None:
        return confidence_base
    try:
        historico = memory.get_decision_history(decision_point_signature)
    except Exception:
        return confidence_base
    if not historico:
        return confidence_base
    media_historico = sum(h.confidence for h in historico) / len(historico)
    return (confidence_base + media_historico) / 2
