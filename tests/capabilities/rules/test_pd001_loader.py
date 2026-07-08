"""Testes do loader do spec bespoke PD-001 (`pd001_loader.py`)."""

from __future__ import annotations

from batman_os.capabilities.rules.pd001_empty_state_sem_cta import RegraPd001Spec
from batman_os.capabilities.rules.pd001_loader import carregar_especificacoes_pd001


class TestCarregarEspecificacoesPd001:
    def test_carrega_o_codigo_pd001(self) -> None:
        specs = carregar_especificacoes_pd001()

        codigos = {item["regra"].codigo for item in specs}
        assert codigos == {"PD-001"}

    def test_toda_regra_e_uma_regrapd001spec_valida(self) -> None:
        specs = carregar_especificacoes_pd001()

        for item in specs:
            assert isinstance(item["regra"], RegraPd001Spec)

    def test_descoberta_e_do_tipo_arvore(self) -> None:
        specs = carregar_especificacoes_pd001()

        for item in specs:
            assert item["descoberta"]["tipo"] == "arvore"
