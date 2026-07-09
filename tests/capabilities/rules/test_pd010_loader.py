"""Testes do loader do spec bespoke PD-010 (`pd010_loader.py`)."""

from __future__ import annotations

from batman_os.capabilities.rules.pd010_loader import carregar_especificacoes_pd010
from batman_os.capabilities.rules.pd010_simulador_sem_piso import RegraPd010Spec


class TestCarregarEspecificacoesPd010:
    def test_carrega_o_codigo_pd010(self) -> None:
        specs = carregar_especificacoes_pd010()

        codigos = {item["regra"].codigo for item in specs}
        assert codigos == {"PD-010"}

    def test_toda_regra_e_uma_regrapd010spec_valida(self) -> None:
        specs = carregar_especificacoes_pd010()

        for item in specs:
            assert isinstance(item["regra"], RegraPd010Spec)

    def test_descoberta_e_do_tipo_pd010(self) -> None:
        specs = carregar_especificacoes_pd010()

        for item in specs:
            assert item["descoberta"]["tipo"] == "pd010"
