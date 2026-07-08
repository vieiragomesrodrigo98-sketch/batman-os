"""Testes do loader do spec bespoke FIN-005 (`fin005_loader.py`)."""

from __future__ import annotations

from batman_os.capabilities.rules.fin005_backtest_sem_oos import RegraFin005Spec
from batman_os.capabilities.rules.fin005_loader import carregar_especificacoes_fin005


class TestCarregarEspecificacoesFin005:
    def test_carrega_o_codigo_fin005(self) -> None:
        specs = carregar_especificacoes_fin005()

        codigos = {item["regra"].codigo for item in specs}
        assert codigos == {"FIN-005"}

    def test_toda_regra_e_uma_regrafin005spec_valida(self) -> None:
        specs = carregar_especificacoes_fin005()

        for item in specs:
            assert isinstance(item["regra"], RegraFin005Spec)

    def test_descoberta_e_do_tipo_arvore(self) -> None:
        specs = carregar_especificacoes_fin005()

        for item in specs:
            assert item["descoberta"]["tipo"] == "arvore"
