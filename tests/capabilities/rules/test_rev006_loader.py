"""Testes do loader do spec bespoke REV-006 (`rev006_loader.py`)."""

from __future__ import annotations

from batman_os.capabilities.rules.rev006_loader import carregar_especificacoes_rev006
from batman_os.capabilities.rules.rev006_variavel_nome_curto import RegraRev006Spec


class TestCarregarEspecificacoesRev006:
    def test_carrega_o_codigo_rev006(self) -> None:
        specs = carregar_especificacoes_rev006()

        codigos = {item["regra"].codigo for item in specs}
        assert codigos == {"REV-006"}

    def test_toda_regra_e_uma_regrarev006spec_valida(self) -> None:
        specs = carregar_especificacoes_rev006()

        for item in specs:
            assert isinstance(item["regra"], RegraRev006Spec)

    def test_descoberta_e_do_tipo_arvore(self) -> None:
        specs = carregar_especificacoes_rev006()

        for item in specs:
            assert item["descoberta"]["tipo"] == "arvore"
