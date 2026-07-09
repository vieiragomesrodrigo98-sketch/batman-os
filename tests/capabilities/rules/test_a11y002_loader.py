"""Testes do loader do spec bespoke A11Y-002 (`a11y002_loader.py`)."""

from __future__ import annotations

from batman_os.capabilities.rules.a11y002_loader import carregar_especificacoes_a11y002
from batman_os.capabilities.rules.a11y002_onclick_sem_teclado import RegraA11y002Spec


class TestCarregarEspecificacoesA11y002:
    def test_carrega_o_codigo_a11y002(self) -> None:
        specs = carregar_especificacoes_a11y002()

        codigos = {item["regra"].codigo for item in specs}
        assert codigos == {"A11Y-002"}

    def test_toda_regra_e_uma_regraa11y002spec_valida(self) -> None:
        specs = carregar_especificacoes_a11y002()

        for item in specs:
            assert isinstance(item["regra"], RegraA11y002Spec)

    def test_descoberta_e_do_tipo_arvore(self) -> None:
        specs = carregar_especificacoes_a11y002()

        for item in specs:
            assert item["descoberta"]["tipo"] == "arvore"
