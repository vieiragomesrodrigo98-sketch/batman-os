"""Vol. II, Cap. 10 — Event Bus.

Log imutavel e append-only: fonte de verdade de tudo que acontece no Kernel
(ADR-0003, Event Sourcing). Nenhum componente do Kernel guarda estado que nao
seja, em ultima instancia, reconstruivel a partir da sequencia de eventos
publicados aqui.

Fonte da verdade: docs/spec/02-kernel/06-event-bus-scheduler.md
"""

from __future__ import annotations

import sqlite3
import threading
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

    `db_path` (Milestone 5 desta construção — escopo de persistência real):
    log append-only via SQLite, não mais em memória Python — sobrevive a
    destruir e recriar o processo apontando para o mesmo arquivo.
    `":memory:"` (default) preserva o comportamento anterior (cada
    `EventBus()` com seu próprio log isolado, nunca compartilhado entre
    instâncias) — nenhum consumidor existente muda, `publish()`/
    `subscribe()`/`replay()` mantêm a MESMA assinatura pública.
    Assinantes (`subscribe`) continuam em memória Python: são construção
    em tempo de execução, não fazem parte do log que precisa sobreviver a
    reiniciar o processo.

    Thread-safety (Fase 2 do roadmap de plataforma, `.claude/plans/
    peaceful-wondering-hearth.md`, Estagio 2.3) — `check_same_thread=False`
    permite a mesma conexao ser usada por Missoes rodando em threads
    diferentes (pre-requisito para o Scheduler real, Estagio 2.4); um
    `threading.Lock()` explicito serializa toda escrita/leitura (evita
    "database is locked" sob contencao e garante que `replay()` nunca veja
    um estado parcialmente escrito). `WAL` melhora concorrencia leitura/
    escrita em disco real — sem efeito (e sem custo) em `:memory:`."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._lock = threading.Lock()
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS events ("
            "seq INTEGER PRIMARY KEY AUTOINCREMENT, "
            "mission_id TEXT NOT NULL, "
            "payload_json TEXT NOT NULL"
            ")"
        )
        if db_path != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.commit()
        self._assinantes: list[tuple[EventFilter, EventHandler]] = []

    def publish(self, event: KernelEvent) -> None:
        """Publica um evento. Ordenacao causal (Vol.II Cap.10, secao 10.2.1)
        e garantida por construcao: eventos da mesma missao sao sempre
        appendados na ordem em que `publish()` e chamado (`seq` autoincrement
        do SQLite preserva essa ordem para `replay()`)."""
        with self._lock:
            self._conn.execute(
                "INSERT INTO events (mission_id, payload_json) VALUES (?, ?)",
                (str(event.mission_id), event.model_dump_json()),
            )
            self._conn.commit()
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
        with self._lock:
            cursor = self._conn.execute(
                "SELECT payload_json FROM events WHERE mission_id = ? ORDER BY seq ASC",
                (str(mission_id),),
            )
            linhas = cursor.fetchall()
        return [KernelEvent.model_validate_json(linha[0]) for linha in linhas]
