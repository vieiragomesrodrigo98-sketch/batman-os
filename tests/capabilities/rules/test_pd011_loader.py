"""Testes do loader do spec bespoke PD-011 (`pd011_loader.py`)."""

from __future__ import annotations

from batman_os.capabilities.rules.pd011_diversificacao_nao_comunicada import RegraPd011Spec
from batman_os.capabilities.rules.pd011_loader import carregar_especificacoes_pd011


class TestCarregarEspecificacoesPd011:
    def test_carrega_o_codigo_pd011(self) -> None:
        specs = carregar_especificacoes_pd011()

        codigos = {item["regra"].codigo for item in specs}
        assert codigos == {"PD-011"}

    def test_toda_regra_e_uma_regrapd011spec_valida(self) -> None:
        specs = carregar_especificacoes_pd011()

        for item in specs:
            assert isinstance(item["regra"], RegraPd011Spec)

    def test_descoberta_e_do_tipo_pd011(self) -> None:
        specs = carregar_especificacoes_pd011()

        for item in specs:
            assert item["descoberta"]["tipo"] == "pd011"
