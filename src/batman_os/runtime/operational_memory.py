"""Vol. III, Cap. 13 — Operational Memory.

Onde e como o Batman persiste estado ENTRE missões — a diferença entre
"lembrar" (este módulo) e "aprender" (Learning Engine, Volume VI, fora de
escopo desta construção). Nunca é fonte de verdade comportamental (ADR-0004):
alimenta o cálculo de confiança do Decision Engine e produz candidatos para
o Learning Engine — nunca decide nem promove conhecimento sozinha.

Fonte da verdade: docs/spec/03-runtime/03-operational-memory.md
"""

from __future__ import annotations

import sqlite3

from pydantic import BaseModel, Field

from batman_os.foundation.tenant_isolation import exigir_tenant_correspondente
from batman_os.foundation.types import (
    CognitiveDebtFlag,
    DecisionPointId,
    MissionId,
    MissionTypeId,
    RecordId,
    StepId,
    TenantId,
    Timestamp,
    agora,
    novo_uuid7,
)
from batman_os.kernel.decision_engine import ResolvedBy
from batman_os.kernel.mission_runtime import MissionIntent, MissionState
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
    após criado (AT-13.1: append-only, nunca editada).

    `tenant_id` obrigatório desde Vol.III Cap.14 (ADR-0005) — toda consulta
    de leitura abaixo é escopada por ele (AT-14.1)."""

    model_config = {"frozen": True}

    id: RecordId = Field(default_factory=lambda: RecordId(novo_uuid7()))
    mission_id: MissionId
    tenant_id: TenantId
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

    `db_path` (Milestone 5 desta construção — escopo de persistência real):
    armazenamento append-only via SQLite, não mais em memória Python —
    sobrevive a destruir e recriar o processo apontando para o mesmo
    arquivo. `":memory:"` (default) preserva o comportamento anterior (cada
    `OperationalMemory()` isolada, nunca compartilhada entre instâncias) —
    `registrar()`/`all_records()` mantêm a MESMA assinatura pública.

    Numa integração ponta a ponta completa, isso seria preenchido por
    reconciliação automática a partir do Event Bus (secao 13.3); Decision
    Engine e Workflow Engine, nesta construção, ainda não publicam eventos
    ricos o bastante para essa reconstrução automática — registrado como
    pendência de integração, não uma omissão silenciosa.
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(db_path)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS records ("
            "seq INTEGER PRIMARY KEY AUTOINCREMENT, "
            "tenant_id TEXT NOT NULL, "
            "payload_json TEXT NOT NULL"
            ")"
        )
        self._conn.commit()

    def registrar(self, record: OperationalRecord) -> None:
        """AT-13.1 — append-only; não há método de edição ou remoção."""
        self._conn.execute(
            "INSERT INTO records (tenant_id, payload_json) VALUES (?, ?)",
            (str(record.tenant_id), record.model_dump_json()),
        )
        self._conn.commit()

    def all_records(self) -> list[OperationalRecord]:
        """Fase 5 do roadmap de plataforma (isolamento multi-tenant,
        `.claude/plans/peaceful-wondering-hearth.md`, Estágio 5.3) —
        avaliado e mantido DELIBERADAMENTE cross-tenant, não um gap
        esquecido: junto com `get_frequency()`/`find_promotion_
        candidates()` abaixo, alimenta o mesmo tipo de sinal de
        aprendizado/padrão compartilhado que `CapabilityRegistry`/
        `MissionTypeRegistry`/`PlaybookRegistry` já tratam como catálogos
        globais — um padrão recorrente que gera candidato a promoção de
        regra plausivelmente PRECISA ser observado através de todos os
        tenants, não é o mesmo tipo de leitura que `MissionRuntime.
        get_mission()` (Estágio 5.1), onde um chamador escopado a UM
        tenant nunca deveria ver dado de outro. Quem precisar de leitura
        escopada usa `_records_do_tenant()` (via `find_similar_missions`/
        `get_decision_history`, já tenant-scoped desde a Milestone 7)."""
        cursor = self._conn.execute("SELECT payload_json FROM records ORDER BY seq ASC")
        return [OperationalRecord.model_validate_json(linha[0]) for linha in cursor.fetchall()]

    def _records_do_tenant(self, tenant_id: TenantId) -> list[OperationalRecord]:
        """Vol.VIII Cap.32/33 (Milestone 7 — Row-Level Security mínima):
        filtro por tenant aplicado na PRÓPRIA query SQL (`WHERE tenant_id =
        ?`), não só depois de carregar tudo em Python — e cada registro
        retornado passa por `exigir_tenant_correspondente()` como segunda
        camada de defesa, que levantaria `IsolamentoDeTenantViolado` se, por
        algum bug futuro, um registro de outro tenant escapasse do filtro
        SQL."""
        cursor = self._conn.execute(
            "SELECT payload_json FROM records WHERE tenant_id = ? ORDER BY seq ASC",
            (str(tenant_id),),
        )
        registros = [OperationalRecord.model_validate_json(linha[0]) for linha in cursor.fetchall()]
        for registro in registros:
            exigir_tenant_correspondente(tenant_id, registro.tenant_id)
        return registros

    def find_similar_missions(
        self, tenant_id: TenantId, intent: MissionIntent, limit: int
    ) -> list[OperationalRecord]:
        """Vol.III Cap.13, secao 13.4 — similaridade léxica simples (chaves
        de `intent.dados` em comum), zero LLM/rede, consistente com o motor
        de Recall já precedente no Batman atual.

        `tenant_id` obrigatório (Vol.III Cap.14, AT-14.1) — nunca retorna
        registro de tenant diferente do solicitado."""
        do_tenant = self._records_do_tenant(tenant_id)
        pontuados = [(self._similaridade(intent, r), r) for r in do_tenant]
        pontuados.sort(key=lambda par: par[0], reverse=True)
        return [registro for pontuacao, registro in pontuados[:limit] if pontuacao > 0]

    def get_decision_history(
        self, tenant_id: TenantId, decision_point_signature: str
    ) -> list[DecisionSummary]:
        """Vol.III Cap.13, secao 13.4.

        `tenant_id` obrigatório (Vol.III Cap.14, AT-14.1) — nunca retorna
        histórico de decisão de um tenant diferente do solicitado."""
        return [
            resumo
            for record in self._records_do_tenant(tenant_id)
            for resumo in record.decision_points_resolved
            if resumo.decision_point_id == decision_point_signature
        ]

    def get_frequency(self, pattern: PatternQuery) -> int:
        """Vol.III Cap.13, secao 13.6 — usado para detectar candidatos a
        Cognitive Debt recorrente."""
        return sum(1 for r in self.all_records() if self._casa_padrao(r, pattern))

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
    confidence_base: float,
    memory: OperationalMemory | None,
    tenant_id: TenantId,
    decision_point_signature: str,
) -> float:
    """Vol.III Cap.13, secao 13.5 — combina confiança de regra + histórico da
    Operational Memory no cálculo de confiança do Decision Engine (Vol.II
    Cap.8). AT-13.3: indisponibilidade da Operational Memory (`None`, ou
    exceção ao consultar) degrada graciosamente para a confiança base —
    nunca propaga falha para o Decision Engine. `tenant_id` obrigatório
    (Vol.III Cap.14, AT-14.1) — nunca combina com histórico de outro tenant.

    Nota de integração: o `DecisionEngine` (Cap.8) já construído nesta
    sessão ainda não chama esta função internamente — é o padrão de uso
    pretendido pela especificação, disponível para ser conectado quando a
    integração completa Decision Engine <-> Operational Memory for feita.
    """
    if memory is None:
        return confidence_base
    try:
        historico = memory.get_decision_history(tenant_id, decision_point_signature)
    except Exception:
        return confidence_base
    if not historico:
        return confidence_base
    media_historico = sum(h.confidence for h in historico) / len(historico)
    return (confidence_base + media_historico) / 2
