"""Testes do loader do spec bespoke SEC-008 (`sec008_loader.py`)."""

from __future__ import annotations

from batman_os.capabilities.rules.sec008_loader import carregar_especificacoes_sec008
from batman_os.capabilities.rules.sec008_role_sem_super_admin import RegraSec008Spec


class TestCarregarEspecificacoesSec008:
    def test_carrega_o_codigo_sec008(self) -> None:
        specs = carregar_especificacoes_sec008()

        codigos = {item["regra"].codigo for item in specs}
        assert codigos == {"SEC-008"}

    def test_toda_regra_e_uma_regrasec008spec_valida(self) -> None:
        specs = carregar_especificacoes_sec008()

        for item in specs:
            assert isinstance(item["regra"], RegraSec008Spec)

    def test_descoberta_e_do_tipo_arvore(self) -> None:
        specs = carregar_especificacoes_sec008()

        for item in specs:
            assert item["descoberta"]["tipo"] == "arvore"
