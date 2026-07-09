"""Testes do loader do spec bespoke SRE-006 (`sre006_loader.py`)."""

from __future__ import annotations

from batman_os.capabilities.rules.sre006_loader import carregar_especificacoes_sre006
from batman_os.capabilities.rules.sre006_timeout_ausente import RegraSre006Spec


class TestCarregarEspecificacoesSre006:
    def test_carrega_o_codigo_sre006(self) -> None:
        specs = carregar_especificacoes_sre006()

        codigos = {item["regra"].codigo for item in specs}
        assert codigos == {"SRE-006"}

    def test_toda_regra_e_uma_regrasre006spec_valida(self) -> None:
        specs = carregar_especificacoes_sre006()

        for item in specs:
            assert isinstance(item["regra"], RegraSre006Spec)

    def test_descoberta_e_do_tipo_sre006(self) -> None:
        specs = carregar_especificacoes_sre006()

        for item in specs:
            assert item["descoberta"]["tipo"] == "sre006"
