"""Testes do loader do spec bespoke CTO-004 (`cto004_loader.py`)."""

from __future__ import annotations

from batman_os.capabilities.rules.cto004_endpoint_sem_doc import RegraCto004Spec
from batman_os.capabilities.rules.cto004_loader import carregar_especificacoes_cto004


class TestCarregarEspecificacoesCto004:
    def test_carrega_o_codigo_cto004(self) -> None:
        specs = carregar_especificacoes_cto004()

        codigos = {item["regra"].codigo for item in specs}
        assert codigos == {"CTO-004"}

    def test_toda_regra_e_uma_regracto004spec_valida(self) -> None:
        specs = carregar_especificacoes_cto004()

        for item in specs:
            assert isinstance(item["regra"], RegraCto004Spec)

    def test_descoberta_e_do_tipo_arvore(self) -> None:
        specs = carregar_especificacoes_cto004()

        for item in specs:
            assert item["descoberta"]["tipo"] == "arvore"
