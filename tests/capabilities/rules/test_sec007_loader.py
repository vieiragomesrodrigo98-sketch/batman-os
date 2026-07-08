"""Testes do loader do spec bespoke SEC-007 (`sec007_loader.py`)."""

from __future__ import annotations

from batman_os.capabilities.rules.sec007_ddl_no_import import RegraSec007Spec
from batman_os.capabilities.rules.sec007_loader import carregar_especificacoes_sec007


class TestCarregarEspecificacoesSec007:
    def test_carrega_o_codigo_sec007(self) -> None:
        specs = carregar_especificacoes_sec007()

        codigos = {item["regra"].codigo for item in specs}
        assert codigos == {"SEC-007"}

    def test_toda_regra_e_uma_regrasec007spec_valida(self) -> None:
        specs = carregar_especificacoes_sec007()

        for item in specs:
            assert isinstance(item["regra"], RegraSec007Spec)

    def test_descoberta_e_do_tipo_arvore(self) -> None:
        specs = carregar_especificacoes_sec007()

        for item in specs:
            assert item["descoberta"]["tipo"] == "arvore"
