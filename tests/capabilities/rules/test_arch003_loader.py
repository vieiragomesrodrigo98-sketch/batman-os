"""Testes do loader do spec bespoke ARCH-003 (`arch003_loader.py`)."""

from __future__ import annotations

from batman_os.capabilities.rules.arch003_loader import carregar_especificacoes_arch003
from batman_os.capabilities.rules.arch003_pagina_orfa import RegraArch003Spec


class TestCarregarEspecificacoesArch003:
    def test_carrega_o_codigo_arch003(self) -> None:
        specs = carregar_especificacoes_arch003()

        codigos = {item["regra"].codigo for item in specs}
        assert codigos == {"ARCH-003"}

    def test_toda_regra_e_uma_regraarch003spec_valida(self) -> None:
        specs = carregar_especificacoes_arch003()

        for item in specs:
            assert isinstance(item["regra"], RegraArch003Spec)

    def test_descoberta_e_do_tipo_arch003(self) -> None:
        specs = carregar_especificacoes_arch003()

        for item in specs:
            assert item["descoberta"]["tipo"] == "arch003"
