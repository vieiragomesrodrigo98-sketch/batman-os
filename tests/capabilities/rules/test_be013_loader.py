"""Testes do loader do spec bespoke BE-013 (`be013_loader.py`)."""

from __future__ import annotations

from batman_os.capabilities.rules.be013_http200_em_except import RegraBe013Spec
from batman_os.capabilities.rules.be013_loader import carregar_especificacoes_be013


class TestCarregarEspecificacoesBe013:
    def test_carrega_o_codigo_be013(self) -> None:
        specs = carregar_especificacoes_be013()

        codigos = {item["regra"].codigo for item in specs}
        assert codigos == {"BE-013"}

    def test_toda_regra_e_uma_regrabe013spec_valida(self) -> None:
        specs = carregar_especificacoes_be013()

        for item in specs:
            assert isinstance(item["regra"], RegraBe013Spec)

    def test_descoberta_e_do_tipo_arvore(self) -> None:
        specs = carregar_especificacoes_be013()

        for item in specs:
            assert item["descoberta"]["tipo"] == "arvore"
