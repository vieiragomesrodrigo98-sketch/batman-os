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

from batman_os.foundation.tenant_isolation import (
    IsolamentoDeTenantViolado,
    exigir_tenant_correspondente,
)
from batman_os.foundation.types import (
    CognitiveDebtFlag,
    DecisionId,
    DegradationRecord,
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

    `PartiallyCompleted` (Volume V, Cap.22, ADR-0009) — estado terminal de
    sucesso parcial, distinto de `PartiallyFailed` (transitorio, Cap.9: uma
    recuperacao em andamento). Adicionado sem redesenho, apenas novas
    entradas em `_TRANSICOES`, exatamente como antecipado quando o Volume V
    ainda nao existia.
    """

    CREATED = "Created"
    PLANNING = "Planning"
    PLANNED = "Planned"
    DECIDING = "Deciding"
    AWAITING_HUMAN = "AwaitingHuman"
    AWAITING_LLM = "AwaitingLLM"
    EXECUTING = "Executing"
    PARTIALLY_FAILED = "PartiallyFailed"
    PARTIALLY_COMPLETED = "PartiallyCompleted"
    COMPLETED = "Completed"
    FAILED = "Failed"
    CANCELLED = "Cancelled"


ESTADOS_TERMINAIS = frozenset(
    {
        MissionState.COMPLETED,
        MissionState.FAILED,
        MissionState.CANCELLED,
        MissionState.PARTIALLY_COMPLETED,
    }
)


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
    WORKFLOW_PARTIALLY_COMPLETED = "WorkflowPartiallyCompleted"  # Vol.V Cap.22, ADR-0009
    WORKFLOW_FAILED = "WorkflowFailed"
    RECOVERY_APPLIED = "RecoveryApplied"
    RECOVERY_EXHAUSTED = "RecoveryExhausted"
    CANCELLATION_REQUESTED = "CancellationRequested"


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
    degradations: list[DegradationRecord] = Field(default_factory=list)


class DegradacaoSemEvidencia(Exception):
    """Vol.V Cap.22, secao 22.4 (AT-22.3) — `PartiallyCompleted` exige ao
    menos uma `DegradationRecord`; nunca um estado de degradacao sem
    evidencia (Evidence First)."""


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
    (
        MissionState.EXECUTING,
        MissionEventType.WORKFLOW_PARTIALLY_COMPLETED,
    ): MissionState.PARTIALLY_COMPLETED,  # Vol.V Cap.22, secao 22.4.1
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
        self._publicar(
            mission,
            "MissionCreated",
            payload_extra={"tipo": str(mission.tipo), "intent": mission.intent.dados},
        )
        return mission

    def transition(
        self,
        mission_id: MissionId,
        evento: MissionEventType,
        tenant_id: TenantId,
        payload_extra: dict[str, Any] | None = None,
        degradations: list[DegradationRecord] | None = None,
    ) -> Mission:
        """Vol.II Cap.6, secao 6.4. Toda transicao publica automaticamente um
        evento no Event Bus (AT-6.2) — nao ha caminho de mutacao de estado que
        nao passe por aqui.

        `degradations` (Vol.V Cap.22, secao 22.4, AT-22.3) — obrigatorio e
        nao-vazio quando a transicao leva a `PartiallyCompleted`; nunca um
        estado de degradacao sem evidencia (Evidence First).

        `tenant_id` obrigatorio desde a Fase 9 do roadmap de plataforma
        (`.claude/plans/peaceful-wondering-hearth.md`, Estagio 9.1) — antes,
        `transition()` confiava que todo chamador ja era interno e
        confiavel (Fase 5, Estagio 5.1); a Fase 8 (autenticacao real da
        API) provou esse pressuposto errado na pratica: o gate `get_mission
        (mid, tenant_id)` que os handlers HTTP ja chamavam antes de mutar
        so era defesa real porque o `tenant_id` la vem de uma chave
        autenticada — mas o Kernel em si nunca impunha isso, dependendo de
        disciplina manual em cada chamador novo. Mesma semantica de erro
        de `get_mission()`: mismatch levanta a MESMA excecao de "nao
        encontrada", nunca uma distinta."""
        mission = self._buscar_mission(mission_id)
        try:
            exigir_tenant_correspondente(tenant_id, mission.tenant_id)
        except IsolamentoDeTenantViolado as erro:
            raise KeyError(f"Missao desconhecida: {mission_id}") from erro
        chave = (mission.estado, evento)
        se_desconhecida = chave not in _TRANSICOES
        if se_desconhecida:
            raise TransicaoInvalida(
                f"Missao {mission_id} nao pode processar '{evento.value}' "
                f"estando em '{mission.estado.value}'"
            )

        novo_estado = _TRANSICOES[chave]

        if novo_estado == MissionState.PARTIALLY_COMPLETED and not degradations:
            raise DegradacaoSemEvidencia(
                f"Missao {mission_id} nao pode transicionar para PartiallyCompleted "
                "sem ao menos uma DegradationRecord (AT-22.3)"
            )

        mission.estado = novo_estado
        mission.atualizado_em = agora()
        if degradations:
            mission.degradations.extend(degradations)

        if novo_estado in ESTADOS_TERMINAIS and mission.cognitive_debt_flag is None:
            mission.cognitive_debt_flag = self._calcular_cognitive_debt_flag(mission.id)

        self._publicar(
            mission,
            f"Mission{novo_estado.value}",
            payload_extra={
                "evento": evento.value,
                **(
                    {"degradations": [d.model_dump(mode="json") for d in degradations]}
                    if degradations
                    else {}
                ),
                **(payload_extra or {}),
            },
        )
        return mission

    def get_state(self, mission_id: MissionId, tenant_id: TenantId) -> MissionState:
        return self.get_mission(mission_id, tenant_id).estado

    def get_mission(self, mission_id: MissionId, tenant_id: TenantId) -> Mission:
        """Fase 5 do roadmap de plataforma (isolamento multi-tenant,
        `.claude/plans/peaceful-wondering-hearth.md`, Estagio 5.1) —
        `tenant_id` obrigatorio: fecha o gap real de acesso de leitura
        cross-tenant (achado de investigacao direta, nao hipotetico —
        antes, qualquer chamador com um `mission_id` valido conseguia ler
        a Missao de QUALQUER tenant). Mismatch levanta a MESMA excecao de
        "nao encontrada" que um `mission_id` inexistente (nunca uma
        excecao distinta que revelaria "existe, mas nao e seu" — evita
        enumeracao entre tenants, pratica padrao de seguranca).

        `transition()` ganhou a MESMA validacao na Fase 9, Estagio 9.1 —
        ver sua docstring."""
        mission = self._buscar_mission(mission_id)
        try:
            exigir_tenant_correspondente(tenant_id, mission.tenant_id)
        except IsolamentoDeTenantViolado as erro:
            raise KeyError(f"Missao desconhecida: {mission_id}") from erro
        return mission

    def _buscar_mission(self, mission_id: MissionId) -> Mission:
        """Fase 2 do roadmap de plataforma (persistencia hibrida,
        `.claude/plans/peaceful-wondering-hearth.md`, Estagio 2.1) —
        cache-miss (`mission_id` ausente do `dict` em memoria, ex.:
        processo reiniciado) hidrata a Missao via replay do Event Bus antes
        de desistir. Caminho quente (Missao ja presente) inalterado.

        Busca RAW, sem checagem de tenant — `transition()` (desde a Fase 9,
        Estagio 9.1) e `get_mission()` fazem a validacao SEPARADAMENTE,
        logo apos chamar esta funcao (nao delegam a checagem pra ca, pra
        preservar esta funcao como primitivo puro de busca)."""
        if mission_id not in self._missions:
            hidratada = self._hidratar_de(mission_id)
            if hidratada is None:
                raise KeyError(f"Missao desconhecida: {mission_id}")
            self._missions[mission_id] = hidratada
            return hidratada
        return self._missions[mission_id]

    def _hidratar_de(self, mission_id: MissionId) -> Mission | None:
        """Reconstrucao via replay do Event Bus, generalizando o padrao que
        `_calcular_cognitive_debt_flag` ja aplicava a 1 campo — aqui para a
        `Mission` inteira. So chamada em cache-miss (nunca no caminho
        quente); retorna `None` se `mission_id` nunca existiu de fato."""
        historia = self._event_bus.replay(mission_id)
        criado = next((e for e in historia if e.tipo == "MissionCreated"), None)
        if criado is None:
            return None

        tipo_raw = criado.payload.get("tipo", "")
        mission = Mission(
            id=mission_id,
            tenant_id=criado.tenant_id,
            tipo=MissionTypeId(tipo_raw),
            intent=MissionIntent(dados=criado.payload.get("intent", {})),
            criado_em=criado.ocorrido_em,
        )
        for evento in historia:
            # Fase 2 Estagio 2.5 — achado ao testar retomada ponta-a-ponta:
            # desde que o WorkflowEngine tambem publica no MESMO EventBus
            # sob o mesmo mission_id (Estagio 2.1), o replay() mistura
            # eventos de Mission E de WorkflowRun. Ambos carregam uma chave
            # "estado", mas em dominios de enum DIFERENTES (MissionState vs.
            # EstadoWorkflowRun) — sem filtrar por emissor, um "estado":
            # "running" do WorkflowRun quebrava `MissionState("running")`.
            if evento.emitido_por != EmissorKernel.MISSION_RUNTIME:
                continue
            estado_raw = evento.payload.get("estado")
            if estado_raw is not None:
                mission.estado = MissionState(estado_raw)
            mission.atualizado_em = evento.ocorrido_em
            degradations_raw = evento.payload.get("degradations")
            if degradations_raw:
                mission.degradations.extend(
                    DegradationRecord.model_validate(d) for d in degradations_raw
                )

        if mission.estado in ESTADOS_TERMINAIS:
            mission.cognitive_debt_flag = self._calcular_cognitive_debt_flag(mission_id)
        return mission

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
