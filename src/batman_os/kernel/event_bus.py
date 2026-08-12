"""Vol. II, Cap. 10 — Event Bus.

Log imutavel e append-only: fonte de verdade de tudo que acontece no Kernel
(ADR-0003, Event Sourcing). Nenhum componente do Kernel guarda estado que nao
seja, em ultima instancia, reconstruivel a partir da sequencia de eventos
publicados aqui.

Fonte da verdade: docs/spec/02-kernel/06-event-bus-scheduler.md
"""

from __future__ import annotations

import logging
import os
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

logger = logging.getLogger(__name__)

#: Teto de eventos retidos entre execuções, e a aritmética que o escolheu.
#:
#: Medido em 2026-08-12 (`GOV_BATMANOS_ESTADO_DB_16GB01`): **2.770 bytes por
#: evento** (19.688.812.544 bytes / 7.108.502 eventos), e um scan do
#: radar-preditivo produz ~748 mil eventos.
#:
#: Com teto de 100.000 o piso fica em ~264 MB, e o pico — durante um scan,
#: quando os eventos novos se somam aos retidos — em ~2,3 GB, devolvido ao
#: piso pela poda da execução seguinte. É o número, não o palpite, que o card
#: pedia: de 18,3 GB SEM TETO para ~2,3 GB de pico limitado.
#:
#: `BATMAN_EVENTS_MAX=0` desliga a retenção (investigação com o log inteiro).
_MAX_EVENTOS_PADRAO = 100_000


def _teto_de_eventos(explicito: int | None) -> int:
    """Argumento explícito vence o ambiente, que vence o default."""
    if explicito is not None:
        return explicito
    bruto = os.environ.get("BATMAN_EVENTS_MAX")
    if bruto is None or not bruto.strip():
        return _MAX_EVENTOS_PADRAO
    try:
        return int(bruto)
    except ValueError:
        # Teto ilegível não pode virar "sem teto" nem derrubar o processo: cai
        # no default e diz por quê. Ficar sem retenção em silêncio é como o
        # arquivo chegou a 18,3 GB.
        logger.warning("BATMAN_EVENTS_MAX inválido (%r) — usando %d", bruto, _MAX_EVENTOS_PADRAO)
        return _MAX_EVENTOS_PADRAO


class EmissorKernel(StrEnum):
    """Vol.II Cap.10, secao 10.2.2 — quem pode publicar um evento.

    `ORCHESTRATION` (Fase 10 do roadmap de plataforma, `.claude/plans/
    peaceful-wondering-hearth.md`, Estagio 10.1) — `orchestration/
    playbook_driver.py` publica `HumanEscalationPending` no momento da
    escalada para humano, mesmo padrao ja usado por `PLANNING_ENGINE`
    (`PlanCreated`)."""

    MISSION_RUNTIME = "MissionRuntime"
    PLANNING_ENGINE = "PlanningEngine"
    DECISION_ENGINE = "DecisionEngine"
    WORKFLOW_ENGINE = "WorkflowEngine"
    SCHEDULER = "Scheduler"
    ORCHESTRATION = "Orchestration"


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

    def __init__(self, db_path: str = ":memory:", max_eventos: int | None = None) -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._lock = threading.Lock()
        self._em_memoria = db_path == ":memory:"
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS events ("
            "seq INTEGER PRIMARY KEY AUTOINCREMENT, "
            "mission_id TEXT NOT NULL, "
            "payload_json TEXT NOT NULL"
            ")"
        )
        # Incidente 2026-07-29: sem este indice, `replay(mission_id)` faz FULL
        # TABLE SCAN — num estado.db acumulado de 624 MB (~300k eventos) cada
        # replay custava 224 ms, e como `_calcular_cognitive_debt_flag` chama
        # replay ao FINAL DE CADA MISSAO (~50k por scan), o scan do
        # radar-preditivo levava ~3 h so nessa query. Com o indice: ~0,1 ms.
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_events_mission_id ON events(mission_id)")
        if db_path != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.commit()
        self._assinantes: list[tuple[EventFilter, EventHandler]] = []
        if not self._em_memoria:
            self._aplicar_retencao(_teto_de_eventos(max_eventos))

    def _aplicar_retencao(self, teto: int) -> None:
        """Poda o log ao teto e devolve o disco — `GOV_BATMANOS_ESTADO_DB_16GB01`.

        Roda UMA vez, no `__init__`, e é isso que a torna segura: `replay()`
        é sempre chamado com o `mission_id` da execução corrente, então
        podar antes da primeira missão só alcança execuções anteriores.
        Depois daqui o log volta a ser estritamente append-only — uma missão
        em voo nunca perde história no meio do caminho.

        O `VACUUM` não é detalhe: `DELETE` só marca páginas como livres e o
        arquivo **não encolhe**. Podar sem VACUUM deixaria os 18,3 GB
        intactos e o card resolvido só no papel.
        """
        if teto <= 0:  # 0 = retenção desligada, para investigação com log inteiro
            return
        with self._lock:
            total = int(self._conn.execute("SELECT COUNT(*) FROM events").fetchone()[0])
            if total <= teto:
                return
            linha = self._conn.execute(
                "SELECT seq FROM events ORDER BY seq DESC LIMIT 1 OFFSET ?", (teto - 1,)
            ).fetchone()
            if linha is None:
                return
            # Avisa ANTES, não depois: a primeira poda de um log que cresceu
            # sem teto reescreve o banco inteiro e segura o processo por
            # minutos. Medido no arquivo de 18,3 GB — sem esta linha o scan
            # parece pendurado no `__init__`, e "parece pendurado" é como se
            # mata uma boa defesa por impaciência.
            logger.info(
                "podando log de eventos: %d -> %d (pode demorar; VACUUM reescreve o banco)",
                total,
                teto,
            )
            self._conn.execute("DELETE FROM events WHERE seq < ?", (linha[0],))
            self._conn.commit()
            # VACUUM não pode rodar dentro de transação — o commit acima fecha a
            # aberta pelo DELETE.
            self._conn.execute("VACUUM")
            self._conn.commit()
            # Em WAL o VACUUM reescreve o banco no LOG; o arquivo principal só
            # encolhe no checkpoint. Sem esta linha o disco só voltaria quando o
            # processo terminasse — medido: 1.044.480 bytes antes e depois da
            # poda, idênticos, com a poda tendo funcionado.
            self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        logger.info(
            "log de eventos podado: %d -> %d eventos (teto=%d, BATMAN_EVENTS_MAX)",
            total,
            teto,
            teto,
        )

    def total_de_eventos(self) -> int:
        """Quantos eventos há no log — usado pela retenção e pelos testes."""
        with self._lock:
            return int(self._conn.execute("SELECT COUNT(*) FROM events").fetchone()[0])

    def fechar(self) -> None:
        """Libera a conexão (e o arquivo). O log em disco sobrevive."""
        with self._lock:
            self._conn.close()

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
