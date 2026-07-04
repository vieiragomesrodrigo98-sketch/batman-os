"""Testes do Event Bus (Vol.II Cap.10) — cobre AT-10.1 e o contrato de
publish/subscribe/replay da secao 10.2-10.5 da especificacao."""

from __future__ import annotations

from batman_os.foundation.types import EventId, MissionId, TenantId
from batman_os.kernel.event_bus import EmissorKernel, EventBus, KernelEvent


def _evento(mission_id: str, tipo: str, causado_por: str | None = None) -> KernelEvent:
    return KernelEvent(
        mission_id=MissionId(mission_id),
        tenant_id=TenantId("tenant-1"),
        tipo=tipo,
        emitido_por=EmissorKernel.MISSION_RUNTIME,
        causado_por=EventId(causado_por) if causado_por else None,
    )


def test_at_10_1_replay_reconstroi_historia_completa_de_uma_missao() -> None:
    bus = EventBus()
    bus.publish(_evento("m-1", "MissionCreated"))
    bus.publish(_evento("m-1", "MissionPlanned"))
    bus.publish(_evento("m-1", "MissionCompleted"))

    historia = bus.replay(MissionId("m-1"))

    assert [e.tipo for e in historia] == [
        "MissionCreated",
        "MissionPlanned",
        "MissionCompleted",
    ]


def test_replay_isola_eventos_de_missoes_diferentes() -> None:
    bus = EventBus()
    bus.publish(_evento("m-1", "MissionCreated"))
    bus.publish(_evento("m-2", "MissionCreated"))
    bus.publish(_evento("m-1", "MissionCompleted"))

    historia_m1 = bus.replay(MissionId("m-1"))
    historia_m2 = bus.replay(MissionId("m-2"))

    assert [e.tipo for e in historia_m1] == ["MissionCreated", "MissionCompleted"]
    assert [e.tipo for e in historia_m2] == ["MissionCreated"]


def test_replay_preserva_ordenacao_causal_de_publicacao() -> None:
    bus = EventBus()
    for i in range(5):
        bus.publish(_evento("m-1", f"Evento{i}"))

    historia = bus.replay(MissionId("m-1"))

    assert [e.tipo for e in historia] == [f"Evento{i}" for i in range(5)]


def test_replay_retorna_copia_nao_afeta_log_interno() -> None:
    bus = EventBus()
    bus.publish(_evento("m-1", "MissionCreated"))

    historia = bus.replay(MissionId("m-1"))
    historia.append(_evento("m-1", "EventoFalso"))

    assert [e.tipo for e in bus.replay(MissionId("m-1"))] == ["MissionCreated"]


def test_evento_e_imutavel() -> None:
    evento = _evento("m-1", "MissionCreated")

    with __import__("pytest").raises(Exception):
        evento.tipo = "Outro"  # type: ignore[misc]


def test_subscribe_recebe_apenas_eventos_que_passam_no_filtro() -> None:
    bus = EventBus()
    recebidos: list[str] = []

    bus.subscribe(
        filtro=lambda e: e.tipo == "MissionCompleted",
        handler=lambda e: recebidos.append(e.tipo),
    )

    bus.publish(_evento("m-1", "MissionCreated"))
    bus.publish(_evento("m-1", "MissionCompleted"))

    assert recebidos == ["MissionCompleted"]


def test_cancelar_inscricao_para_de_receber_eventos() -> None:
    bus = EventBus()
    recebidos: list[str] = []

    assinatura = bus.subscribe(
        filtro=lambda _e: True,
        handler=lambda e: recebidos.append(e.tipo),
    )
    bus.publish(_evento("m-1", "Antes"))
    assinatura.cancelar_inscricao()
    bus.publish(_evento("m-1", "Depois"))

    assert recebidos == ["Antes"]
