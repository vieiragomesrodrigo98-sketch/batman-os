"""Testes do loader do spec bespoke CS-005 (`cs005_loader.py`)."""

from __future__ import annotations

from batman_os.capabilities.rules.cs005_erro_sem_request_id import RegraCs005Spec
from batman_os.capabilities.rules.cs005_loader import carregar_especificacoes_cs005


class TestCarregarEspecificacoesCs005:
    def test_carrega_o_codigo_cs005(self) -> None:
        specs = carregar_especificacoes_cs005()

        codigos = {item["regra"].codigo for item in specs}
        assert codigos == {"CS-005"}

    def test_toda_regra_e_uma_regracs005spec_valida(self) -> None:
        specs = carregar_especificacoes_cs005()

        for item in specs:
            assert isinstance(item["regra"], RegraCs005Spec)

    def test_descoberta_e_do_tipo_cs005(self) -> None:
        specs = carregar_especificacoes_cs005()

        for item in specs:
            assert item["descoberta"]["tipo"] == "cs005"
