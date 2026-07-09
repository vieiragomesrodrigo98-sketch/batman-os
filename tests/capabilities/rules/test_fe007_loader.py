"""Testes do loader do spec bespoke FE-007 (`fe007_loader.py`)."""

from __future__ import annotations

from batman_os.capabilities.rules.fe007_loader import carregar_especificacoes_fe007
from batman_os.capabilities.rules.fe007_nav_lock import RegraFe007Spec


class TestCarregarEspecificacoesFe007:
    def test_carrega_o_codigo_fe007(self) -> None:
        specs = carregar_especificacoes_fe007()

        codigos = {item["regra"].codigo for item in specs}
        assert codigos == {"FE-007"}

    def test_toda_regra_e_uma_regrafe007spec_valida(self) -> None:
        specs = carregar_especificacoes_fe007()

        for item in specs:
            assert isinstance(item["regra"], RegraFe007Spec)

    def test_descoberta_e_do_tipo_arquivo_fixo(self) -> None:
        specs = carregar_especificacoes_fe007()

        for item in specs:
            assert item["descoberta"]["tipo"] == "arquivo_fixo"
