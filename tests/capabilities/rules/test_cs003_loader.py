"""Testes do loader do spec bespoke CS-003 (`cs003_loader.py`)."""

from __future__ import annotations

from batman_os.capabilities.rules.cs003_except_pass import RegraCs003Spec
from batman_os.capabilities.rules.cs003_loader import carregar_especificacoes_cs003


class TestCarregarEspecificacoesCs003:
    def test_carrega_o_codigo_cs003(self) -> None:
        specs = carregar_especificacoes_cs003()

        codigos = {item["regra"].codigo for item in specs}
        assert codigos == {"CS-003"}

    def test_toda_regra_e_uma_regracs003spec_valida(self) -> None:
        specs = carregar_especificacoes_cs003()

        for item in specs:
            assert isinstance(item["regra"], RegraCs003Spec)

    def test_descoberta_e_do_tipo_arvore(self) -> None:
        specs = carregar_especificacoes_cs003()

        for item in specs:
            assert item["descoberta"]["tipo"] == "arvore"
