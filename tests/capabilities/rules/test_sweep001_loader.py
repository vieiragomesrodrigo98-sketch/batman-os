"""Testes do loader do spec bespoke SWEEP-001 (`sweep001_loader.py`)."""

from __future__ import annotations

from batman_os.capabilities.rules.sweep001_cadencia_quebrada import RegraSweep001Spec
from batman_os.capabilities.rules.sweep001_loader import carregar_especificacoes_sweep001


class TestCarregarEspecificacoesSweep001:
    def test_carrega_o_codigo_sweep001(self) -> None:
        specs = carregar_especificacoes_sweep001()

        codigos = {item["regra"].codigo for item in specs}
        assert codigos == {"SWEEP-001"}

    def test_toda_regra_e_uma_regrasweep001spec_valida(self) -> None:
        specs = carregar_especificacoes_sweep001()

        for item in specs:
            assert isinstance(item["regra"], RegraSweep001Spec)

    def test_descoberta_e_do_tipo_arquivo_fixo(self) -> None:
        specs = carregar_especificacoes_sweep001()

        for item in specs:
            assert item["descoberta"]["tipo"] == "arquivo_fixo"
