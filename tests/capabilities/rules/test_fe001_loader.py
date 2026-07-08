"""Testes do loader do spec bespoke FE-001 (`fe001_loader.py`)."""

from __future__ import annotations

from batman_os.capabilities.rules.fe001_export_duplicado import RegraFe001Spec
from batman_os.capabilities.rules.fe001_loader import carregar_especificacoes_fe001


class TestCarregarEspecificacoesFe001:
    def test_carrega_o_codigo_fe001(self) -> None:
        specs = carregar_especificacoes_fe001()

        codigos = {item["regra"].codigo for item in specs}
        assert codigos == {"FE-001"}

    def test_toda_regra_e_uma_regrafe001spec_valida(self) -> None:
        specs = carregar_especificacoes_fe001()

        for item in specs:
            assert isinstance(item["regra"], RegraFe001Spec)

    def test_descoberta_e_do_tipo_regex_agregado(self) -> None:
        specs = carregar_especificacoes_fe001()

        for item in specs:
            assert item["descoberta"]["tipo"] == "regex_agregado"
