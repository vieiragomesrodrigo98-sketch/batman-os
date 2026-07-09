"""Testes do loader do spec bespoke CTO-002 (`cto002_loader.py`)."""

from __future__ import annotations

from batman_os.capabilities.rules.cto002_loader import carregar_especificacoes_cto002
from batman_os.capabilities.rules.cto002_rota_sem_versao import RegraCto002Spec


class TestCarregarEspecificacoesCto002:
    def test_carrega_o_codigo_cto002(self) -> None:
        specs = carregar_especificacoes_cto002()

        codigos = {item["regra"].codigo for item in specs}
        assert codigos == {"CTO-002"}

    def test_toda_regra_e_uma_regracto002spec_valida(self) -> None:
        specs = carregar_especificacoes_cto002()

        for item in specs:
            assert isinstance(item["regra"], RegraCto002Spec)

    def test_descoberta_e_do_tipo_arvore(self) -> None:
        specs = carregar_especificacoes_cto002()

        for item in specs:
            assert item["descoberta"]["tipo"] == "arvore"
