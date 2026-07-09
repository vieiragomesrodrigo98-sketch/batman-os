"""Testes do loader do spec bespoke UI-002 (`ui002_loader.py`)."""

from __future__ import annotations

from batman_os.capabilities.rules.ui002_inline_style_estatico import RegraUi002Spec
from batman_os.capabilities.rules.ui002_loader import carregar_especificacoes_ui002


class TestCarregarEspecificacoesUi002:
    def test_carrega_o_codigo_ui002(self) -> None:
        specs = carregar_especificacoes_ui002()

        codigos = {item["regra"].codigo for item in specs}
        assert codigos == {"UI-002"}

    def test_toda_regra_e_uma_regraui002spec_valida(self) -> None:
        specs = carregar_especificacoes_ui002()

        for item in specs:
            assert isinstance(item["regra"], RegraUi002Spec)

    def test_descoberta_e_do_tipo_arvore(self) -> None:
        specs = carregar_especificacoes_ui002()

        for item in specs:
            assert item["descoberta"]["tipo"] == "arvore"
