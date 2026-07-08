"""Testes do loader do spec bespoke BA-005 (`ba005_loader.py`)."""

from __future__ import annotations

from batman_os.capabilities.rules.ba005_divisao_sem_guarda import RegraBa005Spec
from batman_os.capabilities.rules.ba005_loader import carregar_especificacoes_ba005


class TestCarregarEspecificacoesBa005:
    def test_carrega_o_codigo_ba005(self) -> None:
        specs = carregar_especificacoes_ba005()

        codigos = {item["regra"].codigo for item in specs}
        assert codigos == {"BA-005"}

    def test_toda_regra_e_uma_regraba005spec_valida(self) -> None:
        specs = carregar_especificacoes_ba005()

        for item in specs:
            assert isinstance(item["regra"], RegraBa005Spec)

    def test_descoberta_e_do_tipo_arvore(self) -> None:
        specs = carregar_especificacoes_ba005()

        for item in specs:
            assert item["descoberta"]["tipo"] == "arvore"
