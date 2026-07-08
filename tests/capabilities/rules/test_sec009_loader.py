"""Testes do loader do spec bespoke SEC-009 (`sec009_loader.py`)."""

from __future__ import annotations

from batman_os.capabilities.rules.sec009_admin_role_script import RegraSec009Spec
from batman_os.capabilities.rules.sec009_loader import carregar_especificacoes_sec009


class TestCarregarEspecificacoesSec009:
    def test_carrega_o_codigo_sec009(self) -> None:
        specs = carregar_especificacoes_sec009()

        codigos = {item["regra"].codigo for item in specs}
        assert codigos == {"SEC-009"}

    def test_toda_regra_e_uma_regrasec009spec_valida(self) -> None:
        specs = carregar_especificacoes_sec009()

        for item in specs:
            assert isinstance(item["regra"], RegraSec009Spec)

    def test_descoberta_e_do_tipo_arvore(self) -> None:
        specs = carregar_especificacoes_sec009()

        for item in specs:
            assert item["descoberta"]["tipo"] == "arvore"
