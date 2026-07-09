"""Testes do loader do spec bespoke PERF-004 (`perf004_loader.py`)."""

from __future__ import annotations

from batman_os.capabilities.rules.perf004_arquivo_sem_streaming import RegraPerf004Spec
from batman_os.capabilities.rules.perf004_loader import carregar_especificacoes_perf004


class TestCarregarEspecificacoesPerf004:
    def test_carrega_o_codigo_perf004(self) -> None:
        specs = carregar_especificacoes_perf004()

        codigos = {item["regra"].codigo for item in specs}
        assert codigos == {"PERF-004"}

    def test_toda_regra_e_uma_regraperf004spec_valida(self) -> None:
        specs = carregar_especificacoes_perf004()

        for item in specs:
            assert isinstance(item["regra"], RegraPerf004Spec)

    def test_descoberta_e_do_tipo_arvore(self) -> None:
        specs = carregar_especificacoes_perf004()

        for item in specs:
            assert item["descoberta"]["tipo"] == "arvore"
