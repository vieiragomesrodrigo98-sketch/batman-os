"""Testes do loader do spec bespoke QA-AUTO-003 (`qaauto003_loader.py`)."""

from __future__ import annotations

from batman_os.capabilities.rules.qaauto003_loader import carregar_especificacoes_qaauto003
from batman_os.capabilities.rules.qaauto003_smoke_specs_ausentes import RegraQaAuto003Spec


class TestCarregarEspecificacoesQaAuto003:
    def test_carrega_o_codigo_qaauto003(self) -> None:
        specs = carregar_especificacoes_qaauto003()

        codigos = {item["regra"].codigo for item in specs}
        assert codigos == {"QA-AUTO-003"}

    def test_toda_regra_e_uma_regraqaauto003spec_valida(self) -> None:
        specs = carregar_especificacoes_qaauto003()

        for item in specs:
            assert isinstance(item["regra"], RegraQaAuto003Spec)

    def test_descoberta_e_do_tipo_qaauto003(self) -> None:
        specs = carregar_especificacoes_qaauto003()

        for item in specs:
            assert item["descoberta"]["tipo"] == "qaauto003"
