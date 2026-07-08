"""Testes do loader do spec bespoke PD-009 (`pd009_loader.py`)."""

from __future__ import annotations

from batman_os.capabilities.rules.pd009_loader import carregar_especificacoes_pd009
from batman_os.capabilities.rules.pd009_rota_nao_descobrivel import RegraPd009Spec


class TestCarregarEspecificacoesPd009:
    def test_carrega_o_codigo_pd009(self) -> None:
        specs = carregar_especificacoes_pd009()

        codigos = {item["regra"].codigo for item in specs}
        assert codigos == {"PD-009"}

    def test_toda_regra_e_uma_regrapd009spec_valida(self) -> None:
        specs = carregar_especificacoes_pd009()

        for item in specs:
            assert isinstance(item["regra"], RegraPd009Spec)

    def test_descoberta_e_do_tipo_pd009(self) -> None:
        specs = carregar_especificacoes_pd009()

        for item in specs:
            assert item["descoberta"]["tipo"] == "pd009"
