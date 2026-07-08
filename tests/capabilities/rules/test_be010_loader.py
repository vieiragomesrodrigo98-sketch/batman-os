"""Testes do loader do spec bespoke BE-010 (`be010_loader.py`)."""

from __future__ import annotations

from batman_os.capabilities.rules.be010_dependencia_nao_declarada import RegraBe010Spec
from batman_os.capabilities.rules.be010_loader import carregar_especificacoes_be010


class TestCarregarEspecificacoesBe010:
    def test_carrega_o_codigo_be010(self) -> None:
        specs = carregar_especificacoes_be010()

        codigos = {item["regra"].codigo for item in specs}
        assert codigos == {"BE-010"}

    def test_toda_regra_e_uma_regrabe010spec_valida(self) -> None:
        specs = carregar_especificacoes_be010()

        for item in specs:
            assert isinstance(item["regra"], RegraBe010Spec)

    def test_descoberta_e_do_tipo_be010(self) -> None:
        specs = carregar_especificacoes_be010()

        for item in specs:
            assert item["descoberta"]["tipo"] == "be010"
