"""Vol. II, Cap. 10 — Event Bus.

Log imutavel e append-only: fonte de verdade de tudo que acontece no Kernel
(ADR-0003, Event Sourcing). Nenhum componente do Kernel guarda estado que nao
seja, em ultima instancia, reconstruivel a partir da sequencia de eventos
publicados aqui.

Fonte da verdade: docs/spec/02-kernel/06-event-bus-scheduler.md
"""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from batman_os.foundation.types import (
    EventId,
    MissionId,
    TenantId,
    Timestamp,
    agora,
    novo_ulid_like,
)


class EmissorKernel(StrEnum):
    """Vol.II Cap.10, secao 10.2.2 — quem pode publicar um evento."""

    MISSION_RUNTIME = "MissionRuntime"
    PLANNING_ENGINE = "PlanningEngine"
    DECISION_ENGINE = "DecisionEngine"
    WORKFLOW_ENGINE = "WorkflowEngine"
    SCHEDULER = "Scheduler"


class KernelEvent(BaseModel):
    """Vol.II Cap.10, secao 10.2.2 — estrutura de um evento imutavel.

    `tipo` fica como string livre (nao Enum fechado) de proposito: novos tipos
    de evento nascem em capitulos/volumes futuros (ex.: Vol.V introduz
    `PartiallyCompleted`) sem exigir mudanca neste modulo — Evolution Never
    Stops (Principio 10) aplicado ao proprio Event Bus.

    `tenant_id` obrigatorio desde Vol.III Cap.14 (ADR-0005) — propagado
    estruturalmente por toda a cadeia, nenhuma entidade e processada sem ele.
    """

    model_config = {"frozen": True}

    id: EventId = Field(default_factory=lambda: EventId(novo_ulid_like()))
    mission_id: MissionId
    tenant_id: TenantId
    tipo: str
    payload: dict[str, Any] = Field(default_factory=dict)
    emitido_por: EmissorKernel
    ocorrido_em: Timestamp = Field(default_factory=agora)
    causado_por: EventId | None = None


EventFilter = Callable[[KernelEvent], bool]
EventHandler = Callable[[KernelEvent], None]


class Subscription:
    """Alca de cancelamento devolvida por `EventBus.subscribe()`."""

    def __init__(self, cancelar: Callable[[], None]) -> None:
        self._cancelar = cancelar
        self._ativa = True

    def cancelar_inscricao(self) -> None:
        if self._ativa:
            self._cancelar()
            self._ativa = False


class EventBus:
    """Vol.II Cap.10, secao 10.2.3.

    Implementacao de referencia: log append-only em memoria. Persistencia real
    (arquivo, banco, particionamento) e responsabilidade do Volume VIII —
    Infrastructure, ainda nao escrito; este modulo especifica o *contrato*
    (publish/subscribe/replay), nao a infraestrutura final de armazenamento.
    """

    def __init__(self) -> None:
        self._log: list[KernelEvent] = []
        self._assinantes: list[tuple[EventFilter, EventHandler]] = []

    def publish(self, event: KernelEvent) -> None:
        """Publica um evento. Ordenacao causal (Vol.II Cap.10, secao 10.2.1)
        e garantida por construcao: eventos da mesma missao sao sempre
        appendados na ordem em que `publish()` e chamado."""
        self._log.append(event)
        for filtro, handler in list(self._assinantes):
            if filtro(event):
                handler(event)

    def subscribe(self, filtro: EventFilter, handler: EventHandler) -> Subscription:
        """Vol.II Cap.10, secao 10.5 — assinante que cai e volta pode sempre
        recuperar o que perdeu via `replay()`; o Event Bus nao reenvia eventos
        passados automaticamente na inscricao."""
        entrada = (filtro, handler)
        self._assinantes.append(entrada)

        def _cancelar() -> None:
            if entrada in self._assinantes:
                self._assinantes.remove(entrada)

        return Subscription(_cancelar)

    def replay(self, mission_id: MissionId) -> list[KernelEvent]:
        """Vol.II Cap.10, secao 10.2.3 — reconstrucao completa da historia de
        uma missao, na ordem de publicacao (AT-10.1). Retorna uma copia: o
        chamador nunca pode mutar o log interno atraves do valor retornado."""
        return [e for e in self._log if e.mission_id == mission_id]
