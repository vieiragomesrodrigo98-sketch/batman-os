"""Testes do loader do spec bespoke A11Y-003 (`a11y003_loader.py`)."""

from __future__ import annotations

from batman_os.capabilities.rules.a11y003_input_sem_label import RegraA11y003Spec
from batman_os.capabilities.rules.a11y003_loader import carregar_especificacoes_a11y003


class TestCarregarEspecificacoesA11y003:
    def test_carrega_o_codigo_a11y003(self) -> None:
        specs = carregar_especificacoes_a11y003()

        codigos = {item["regra"].codigo for item in specs}
        assert codigos == {"A11Y-003"}

    def test_toda_regra_e_uma_regraa11y003spec_valida(self) -> None:
        specs = carregar_especificacoes_a11y003()

        for item in specs:
            assert isinstance(item["regra"], RegraA11y003Spec)

    def test_descoberta_e_do_tipo_arvore(self) -> None:
        specs = carregar_especificacoes_a11y003()

        for item in specs:
            assert item["descoberta"]["tipo"] == "arvore"
