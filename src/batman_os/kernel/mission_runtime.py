"""Vol. II, Cap. 6 — Mission Runtime.

Ciclo de vida completo de uma Missao: estados, transicoes validas, estrutura
de dados, e o contrato exposto para Planning/Decision/Workflow Engine e
Scheduler (Cap. 7-10).

Fonte da verdade: docs/spec/02-kernel/02-mission-runtime.md
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, Field

from batman_os.foundation.types import (
    DecisionId,
    KnowledgeAssetRef,
    MissionId,
    MissionTypeId,
    PlanId,
    TenantId,
    Timestamp,
    WorkflowRunId,
    agora,
    novo_uuid7,
)
from batman_os.kernel.event_bus import EmissorKernel, EventBus, KernelEvent


class MissionState(StrEnum):
    """Vol.II Cap.6, secao 6.3 — maquina de estados.

    `PartiallyCompleted` (Volume V, Cap.22, ADR-0009) e uma extensao futura
    desta maquina de estados — fora do escopo desta construcao (Volumes I-IV);
    adiciona-la depois nao exige redesenho, apenas novas entradas em
    `_TRANSICOES`.
    """

    CREATED = "Created"
    PLANNING = "Planning"
    PLANNED = "Planned"
    DECIDING = "Deciding"
    AWAITING_HUMAN = "AwaitingHuman"
    AWAITING_LLM = "AwaitingLLM"
    EXECUTING = "Executing"
    PARTIALLY_FAILED = "PartiallyFailed"
    COMPLETED = "Completed"
    FAILED = "Failed"
    CANCELLED = "Cancelled"


ESTADOS_TERMINAIS = frozenset({MissionState.COMPLETED, MissionState.FAILED, MissionState.CANCELLED})


class MissionEventType(StrEnum):
    """Vol.II Cap.6, secao 6.4 — eventos que provocam transicao.

    `PLANNING_STARTED` e `DECIDING_STARTED` nao constam na enumeracao textual
    da secao 6.4, mas sao exigidos pelo proprio diagrama da secao 6.3
    ("Created --> Planning: Planning Engine assume" e "Planned --> Deciding:
    Decision Engine avalia pontos de decisao") para que a maquina de estados
    seja executavel — sem eles nao haveria evento nenhum para disparar essas
    duas transicoes. Adicao mecanica para fechar uma lacuna entre o diagrama
    e a prosa, nao uma decisao arquitetural nova (nao exige ADR).
    """

    PLANNING_STARTED = "PlanningStarted"
    PLAN_READY = "PlanReady"
    PLAN_FAILED = "PlanFailed"
    DECIDING_STARTED = "DecidingStarted"
    DECISIONS_RESOLVED = "DecisionsResolved"
    ESCALATED_TO_HUMAN = "EscalatedToHuman"
    ESCALATED_TO_LLM = "EscalatedToLLM"
    ESCALATION_RESOLVED = "EscalationResolved"
    WORKFLOW_COMPLETED = "WorkflowCompleted"
    WORKFLOW_PARTIALLY_FAILED = "WorkflowPartiallyFailed"
    WORKFLOW_FAILED = "WorkflowFailed"
    RECOVERY_APPLIED = "RecoveryApplied"
    RECOVERY_EXHAUSTED = "RecoveryExhausted"
    CANCELLATION_REQUESTED = "CancellationRequested"


class CognitiveDebtFlag(StrEnum):
    """Vol.I Cap.4, secao 4.9.1 — dado bruto do KPI de Cognitive Debt. So e
    atribuido pelo Mission Runtime, no encerramento da missao (Vol.II Cap.6,
    secao 6.2, nota de design)."""

    AUTONOMOUS = "autonomous"
    HUMAN = "human"
    LLM = "llm"


class MissionIntent(BaseModel):
    """Vol.II Cap.6, secao 6.2 — payload original que originou a Missao. O
    formato interno de `dados` e livre; cada `MissionType` (formalizado no
    Volume V, Cap.20) define o que espera encontrar aqui."""

    dados: dict[str, Any] = Field(default_factory=dict)


class Mission(BaseModel):
    """Vol.II Cap.6, secao 6.2.

    Nota de implementacao: `plan`/`decisions`/`workflowRun` da especificacao
    (objetos embutidos) sao representados aqui como REFERENCIAS (`plan_id`,
    `decision_ids`, `workflow_run_id`) em vez de objetos completos embutidos —
    consistente com Event Sourcing (ADR-0003): cada tipo tem uma unica fonte de
    verdade (seu proprio engine/registro), a Missao apenas correlaciona por ID.

    `tenant_id` obrigatorio desde Vol.III Cap.14 (ADR-0005) — propagado
    estruturalmente por toda a cadeia de dados do Kernel e Runtime.
    """

    id: MissionId = Field(default_factory=lambda: MissionId(novo_uuid7()))
    tenant_id: TenantId
    tipo: MissionTypeId
    intent: MissionIntent
    estado: MissionState = MissionState.CREATED
    plan_id: PlanId | None = None
    decision_ids: list[DecisionId] = Field(default_factory=list)
    workflow_run_id: WorkflowRunId | None = None
    criado_em: Timestamp = Field(default_factory=agora)
    atualizado_em: Timestamp = Field(default_factory=agora)
    parent_mission_id: MissionId | None = None
    knowledge_assets_produzidos: list[KnowledgeAssetRef] = Field(default_factory=list)
    cognitive_debt_flag: CognitiveDebtFlag | None = None


class RegistroTiposDeMissao(Protocol):
    """Vol.V Cap.20, secao 20.2 (AT-20.1) — implementado de verdade pelo
    `MissionTypeRegistry` (Volume V, Cap.20, `workflow/missions.py`).
    Definido aqui como Protocol para o Mission Runtime nao depender do
    pacote `workflow/` (que depende de `kernel/`, nunca o contrario —
    Vol.VIII Cap.32, secao 32.3)."""

    def validar(self, tipo: MissionTypeId) -> None:
        """Levanta excecao se `tipo` nao estiver registrado — 'nao existe
        missao de tipo generico' (secao 20.2)."""
        ...


class TransicaoInvalida(Exception):
    """Vol.II Cap.6, secao 6.3.1, invariante 1 — nenhuma transicao pula
    estados; um evento incompativel com o estado atual e sempre um erro,
    nunca ignorado em silencio."""


# Tabela de transicoes: (estado_atual, evento) -> proximo_estado. Espelha
# exatamente o diagrama da secao 6.3 — nenhuma transicao fora desta tabela e
# aceita (invariante 1).
#
# NOTA (lacuna observada na spec, nao resolvida unilateralmente aqui): o
# diagrama da secao 6.3 so define "-> Cancelled" a partir de Created, Planning,
# Deciding e Executing. Planned/AwaitingHuman/AwaitingLLM/PartiallyFailed nao
# tem caminho para Cancelled no texto atual — mantido fiel ao diagrama
# (regra de ouro do README: a especificacao vence ate ADR formal), sinalizado
# aqui para confirmacao futura com o autor da spec.
_TRANSICOES: dict[tuple[MissionState, MissionEventType], MissionState] = {
    (MissionState.CREATED, MissionEventType.PLANNING_STARTED): MissionState.PLANNING,
    (MissionState.CREATED, MissionEventType.CANCELLATION_REQUESTED): MissionState.CANCELLED,
    (MissionState.PLANNING, MissionEventType.PLAN_READY): MissionState.PLANNED,
    (MissionState.PLANNING, MissionEventType.PLAN_FAILED): MissionState.FAILED,
    (MissionState.PLANNING, MissionEventType.CANCELLATION_REQUESTED): MissionState.CANCELLED,
    (MissionState.PLANNED, MissionEventType.DECIDING_STARTED): MissionState.DECIDING,
    (MissionState.DECIDING, MissionEventType.DECISIONS_RESOLVED): MissionState.EXECUTING,
    (MissionState.DECIDING, MissionEventType.ESCALATED_TO_HUMAN): MissionState.AWAITING_HUMAN,
    (MissionState.DECIDING, MissionEventType.ESCALATED_TO_LLM): MissionState.AWAITING_LLM,
    (MissionState.DECIDING, MissionEventType.CANCELLATION_REQUESTED): MissionState.CANCELLED,
    (MissionState.AWAITING_HUMAN, MissionEventType.ESCALATION_RESOLVED): MissionState.DECIDING,
    (MissionState.AWAITING_LLM, MissionEventType.ESCALATION_RESOLVED): MissionState.DECIDING,
    (MissionState.EXECUTING, MissionEventType.WORKFLOW_COMPLETED): MissionState.COMPLETED,
    (
        MissionState.EXECUTING,
        MissionEventType.WORKFLOW_PARTIALLY_FAILED,
    ): MissionState.PARTIALLY_FAILED,
    (MissionState.EXECUTING, MissionEventType.WORKFLOW_FAILED): MissionState.FAILED,
    (MissionState.EXECUTING, MissionEventType.CANCELLATION_REQUESTED): MissionState.CANCELLED,
    (MissionState.PARTIALLY_FAILED, MissionEventType.RECOVERY_APPLIED): MissionState.EXECUTING,
    (MissionState.PARTIALLY_FAILED, MissionEventType.RECOVERY_EXHAUSTED): MissionState.FAILED,
}

# Eventos de escalonamento cuja ocorrencia na historia de uma Missao decide o
# cognitive_debt_flag final (Vol.I Cap.4 secao 4.9.1). Empate (escalou para
# humano E para LLM em pontos de decisao diferentes) resolve para "human":
# e o sinal de menor autonomia entre os dois, e o mais caro dos dois recursos
# (Principio 5, Human Last) — escolha de desempate documentada aqui por nao
# estar explicita na especificacao.
_TIPO_EVENTO_ESCALACAO_HUMANO = f"Mission{MissionState.AWAITING_HUMAN.value}"
_TIPO_EVENTO_ESCALACAO_LLM = f"Mission{MissionState.AWAITING_LLM.value}"


class MissionRuntime:
    """Vol.II Cap.6, secao 6.4 — interface do Mission Runtime."""

    def __init__(self, event_bus: EventBus, tipos: RegistroTiposDeMissao) -> None:
        self._event_bus = event_bus
        self._tipos = tipos
        self._missions: dict[MissionId, Mission] = {}

    def create(
        self,
        intent: MissionIntent,
        tipo: MissionTypeId,
        tenant_id: TenantId,
        parent_mission_id: MissionId | None = None,
    ) -> Mission:
        """Vol.II Cap.6, secao 6.5 — cria a Missao em `Created` e publica
        `MissionCreated`. Nao inicia planejamento sozinha: quem orquestra a
        chamada seguinte a `transition(id, PLANNING_STARTED)` e o Kernel
        (Cap.5), nao o Mission Runtime — preserva a separacao de camadas
        da ADR-0002.

        `tenant_id` obrigatorio (Vol.III Cap.14, ADR-0005) — propagado a
        toda missao filha e a todo evento publicado a partir daqui.

        `tipo` deve estar registrado em `RegistroTiposDeMissao` (Vol.V
        Cap.20, AT-20.1) — nao existe missao de tipo generico."""
        self._tipos.validar(tipo)
        mission = Mission(
            tenant_id=tenant_id, tipo=tipo, intent=intent, parent_mission_id=parent_mission_id
        )
        self._missions[mission.id] = mission
        self._publicar(mission, "MissionCreated")
        return mission

    def transition(
        self,
        mission_id: MissionId,
        evento: MissionEventType,
        payload_extra: dict[str, Any] | None = None,
    ) -> Mission:
        """Vol.II Cap.6, secao 6.4. Toda transicao publica automaticamente um
        evento no Event Bus (AT-6.2) — nao ha caminho de mutacao de estado que
        nao passe por aqui."""
        mission = self.get_mission(mission_id)
        chave = (mission.estado, evento)
        se_desconhecida = chave not in _TRANSICOES
        if se_desconhecida:
            raise TransicaoInvalida(
                f"Missao {mission_id} nao pode processar '{evento.value}' "
                f"estando em '{mission.estado.value}'"
            )

        novo_estado = _TRANSICOES[chave]
        mission.estado = novo_estado
        mission.atualizado_em = agora()

        if novo_estado in ESTADOS_TERMINAIS and mission.cognitive_debt_flag is None:
            mission.cognitive_debt_flag = self._calcular_cognitive_debt_flag(mission.id)

        self._publicar(
            mission,
            f"Mission{novo_estado.value}",
            payload_extra={"evento": evento.value, **(payload_extra or {})},
        )
        return mission

    def get_state(self, mission_id: MissionId) -> MissionState:
        return self.get_mission(mission_id).estado

    def get_mission(self, mission_id: MissionId) -> Mission:
        if mission_id not in self._missions:
            raise KeyError(f"Missao desconhecida: {mission_id}")
        return self._missions[mission_id]

    def _calcular_cognitive_debt_flag(self, mission_id: MissionId) -> CognitiveDebtFlag:
        """Vol.I Cap.4, secao 4.9.1 (AT-6.1) — deriva o flag a partir da
        propria historia de eventos da missao no Event Bus (nunca consultando
        o Decision Engine diretamente — Mission Runtime nao depende de outro
        engine para fechar sua propria contabilidade, ADR-0002)."""
        historia = self._event_bus.replay(mission_id)
        tipos = {e.tipo for e in historia}
        if _TIPO_EVENTO_ESCALACAO_HUMANO in tipos:
            return CognitiveDebtFlag.HUMAN
        if _TIPO_EVENTO_ESCALACAO_LLM in tipos:
            return CognitiveDebtFlag.LLM
        return CognitiveDebtFlag.AUTONOMOUS

    def _publicar(
        self,
        mission: Mission,
        tipo_evento: str,
        payload_extra: dict[str, Any] | None = None,
    ) -> None:
        self._event_bus.publish(
            KernelEvent(
                mission_id=mission.id,
                tenant_id=mission.tenant_id,
                tipo=tipo_evento,
                emitido_por=EmissorKernel.MISSION_RUNTIME,
                payload={"estado": mission.estado.value, **(payload_extra or {})},
            )
        )
