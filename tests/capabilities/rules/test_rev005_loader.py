"""Testes do loader do spec bespoke REV-005 (`rev005_loader.py`)."""

from __future__ import annotations

from batman_os.capabilities.rules.rev005_bloco_duplicado import RegraRev005Spec
from batman_os.capabilities.rules.rev005_loader import carregar_especificacoes_rev005


class TestCarregarEspecificacoesRev005:
    def test_carrega_o_codigo_rev005(self) -> None:
        specs = carregar_especificacoes_rev005()

        codigos = {item["regra"].codigo for item in specs}
        assert codigos == {"REV-005"}

    def test_toda_regra_e_uma_regrarev005spec_valida(self) -> None:
        specs = carregar_especificacoes_rev005()

        for item in specs:
            assert isinstance(item["regra"], RegraRev005Spec)

    def test_descoberta_e_do_tipo_rev005(self) -> None:
        specs = carregar_especificacoes_rev005()

        for item in specs:
            assert item["descoberta"]["tipo"] == "rev005"
