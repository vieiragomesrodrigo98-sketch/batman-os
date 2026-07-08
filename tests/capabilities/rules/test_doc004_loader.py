"""Testes do loader do spec bespoke DOC-004 (`doc004_loader.py`)."""

from __future__ import annotations

from batman_os.capabilities.rules.doc004_changelog_sem_versao import RegraDoc004Spec
from batman_os.capabilities.rules.doc004_loader import carregar_especificacoes_doc004


class TestCarregarEspecificacoesDoc004:
    def test_carrega_o_codigo_doc004(self) -> None:
        specs = carregar_especificacoes_doc004()

        codigos = {item["regra"].codigo for item in specs}
        assert codigos == {"DOC-004"}

    def test_toda_regra_e_uma_regradoc004spec_valida(self) -> None:
        specs = carregar_especificacoes_doc004()

        for item in specs:
            assert isinstance(item["regra"], RegraDoc004Spec)

    def test_descoberta_e_do_tipo_doc004(self) -> None:
        specs = carregar_especificacoes_doc004()

        for item in specs:
            assert item["descoberta"]["tipo"] == "doc004"
