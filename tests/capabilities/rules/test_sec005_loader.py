"""Testes do loader do spec bespoke SEC-005 (`sec005_loader.py`)."""

from __future__ import annotations

from batman_os.capabilities.rules.sec005_fstring_sql import RegraSec005Spec
from batman_os.capabilities.rules.sec005_loader import carregar_especificacoes_sec005


class TestCarregarEspecificacoesSec005:
    def test_carrega_o_codigo_sec005(self) -> None:
        specs = carregar_especificacoes_sec005()

        codigos = {item["regra"].codigo for item in specs}
        assert codigos == {"SEC-005"}

    def test_toda_regra_e_uma_regrasec005spec_valida(self) -> None:
        specs = carregar_especificacoes_sec005()

        for item in specs:
            assert isinstance(item["regra"], RegraSec005Spec)

    def test_descoberta_e_do_tipo_arvore(self) -> None:
        specs = carregar_especificacoes_sec005()

        for item in specs:
            assert item["descoberta"]["tipo"] == "arvore"
