"""Testes do loader do spec bespoke BA-004 (`ba004_loader.py`)."""

from __future__ import annotations

from batman_os.capabilities.rules.ba004_loader import carregar_especificacoes_ba004
from batman_os.capabilities.rules.ba004_logica_negocio_router import RegraBa004Spec


class TestCarregarEspecificacoesBa004:
    def test_carrega_o_codigo_ba004(self) -> None:
        specs = carregar_especificacoes_ba004()

        codigos = {item["regra"].codigo for item in specs}
        assert codigos == {"BA-004"}

    def test_toda_regra_e_uma_regraba004spec_valida(self) -> None:
        specs = carregar_especificacoes_ba004()

        for item in specs:
            assert isinstance(item["regra"], RegraBa004Spec)

    def test_descoberta_e_do_tipo_arvore(self) -> None:
        specs = carregar_especificacoes_ba004()

        for item in specs:
            assert item["descoberta"]["tipo"] == "arvore"
