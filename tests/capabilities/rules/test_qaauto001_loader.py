"""Testes do loader do spec bespoke QA-AUTO-001 (`qaauto001_loader.py`)."""

from __future__ import annotations

from batman_os.capabilities.rules.qaauto001_loader import carregar_especificacoes_qaauto001
from batman_os.capabilities.rules.qaauto001_router_sem_teste import RegraQaAuto001Spec


class TestCarregarEspecificacoesQaAuto001:
    def test_carrega_o_codigo_qaauto001(self) -> None:
        specs = carregar_especificacoes_qaauto001()

        codigos = {item["regra"].codigo for item in specs}
        assert codigos == {"QA-AUTO-001"}

    def test_toda_regra_e_uma_regraqaauto001spec_valida(self) -> None:
        specs = carregar_especificacoes_qaauto001()

        for item in specs:
            assert isinstance(item["regra"], RegraQaAuto001Spec)

    def test_descoberta_e_do_tipo_qaauto001(self) -> None:
        specs = carregar_especificacoes_qaauto001()

        for item in specs:
            assert item["descoberta"]["tipo"] == "qaauto001"
