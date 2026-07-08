"""Testes do loader do spec bespoke SUP-001 (`sup001_loader.py`)."""

from __future__ import annotations

from batman_os.capabilities.rules.sup001_excecao_silenciada import RegraSup001Spec
from batman_os.capabilities.rules.sup001_loader import carregar_especificacoes_sup001


class TestCarregarEspecificacoesSup001:
    def test_carrega_o_codigo_sup001(self) -> None:
        specs = carregar_especificacoes_sup001()

        codigos = {item["regra"].codigo for item in specs}
        assert codigos == {"SUP-001"}

    def test_toda_regra_e_uma_regrasup001spec_valida(self) -> None:
        specs = carregar_especificacoes_sup001()

        for item in specs:
            assert isinstance(item["regra"], RegraSup001Spec)

    def test_descoberta_e_do_tipo_arvore(self) -> None:
        specs = carregar_especificacoes_sup001()

        for item in specs:
            assert item["descoberta"]["tipo"] == "arvore"
