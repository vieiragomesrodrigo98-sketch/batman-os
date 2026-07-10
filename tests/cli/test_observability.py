"""Testes de `cli/observability.py::linha_do_tempo` — a "Mission
Timeline" do roadmap de plataforma."""

from __future__ import annotations

from batman_os.cli.observability import linha_do_tempo
from batman_os.foundation.types import MissionId, TenantId
from batman_os.kernel.event_bus import EmissorKernel, EventBus, KernelEvent


class TestLinhaDoTempo:
    def test_retorna_vazio_para_missao_sem_eventos(self) -> None:
        bus = EventBus()

        assert linha_do_tempo(bus, MissionId("m-sem-eventos")) == []

    def test_formata_eventos_na_ordem_de_publicacao(self) -> None:
        bus = EventBus()
        mission_id = MissionId("m-1")
        bus.publish(
            KernelEvent(
                mission_id=mission_id,
                tenant_id=TenantId("t-1"),
                tipo="MissionCreated",
                emitido_por=EmissorKernel.MISSION_RUNTIME,
                payload={"estado": "Created"},
            )
        )
        bus.publish(
            KernelEvent(
                mission_id=mission_id,
                tenant_id=TenantId("t-1"),
                tipo="MissionPlanned",
                emitido_por=EmissorKernel.MISSION_RUNTIME,
                payload={"estado": "Planned", "capability_id": "rev005-bloco-duplicado"},
            )
        )

        linhas = linha_do_tempo(bus, mission_id)

        assert len(linhas) == 2
        assert "MissionCreated" in linhas[0]
        assert "MissionPlanned" in linhas[1]
        assert "capability_id=rev005-bloco-duplicado" in linhas[1]
        assert "estado=" not in linhas[1]

    def test_nao_mistura_eventos_de_missoes_diferentes(self) -> None:
        bus = EventBus()
        bus.publish(
            KernelEvent(
                mission_id=MissionId("m-a"),
                tenant_id=TenantId("t-1"),
                tipo="MissionCreated",
                emitido_por=EmissorKernel.MISSION_RUNTIME,
                payload={},
            )
        )
        bus.publish(
            KernelEvent(
                mission_id=MissionId("m-b"),
                tenant_id=TenantId("t-1"),
                tipo="MissionCreated",
                emitido_por=EmissorKernel.MISSION_RUNTIME,
                payload={},
            )
        )

        assert len(linha_do_tempo(bus, MissionId("m-a"))) == 1
        assert len(linha_do_tempo(bus, MissionId("m-b"))) == 1
