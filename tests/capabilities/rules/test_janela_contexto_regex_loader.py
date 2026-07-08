"""Testes do loader dos specs da Skill "janela de contexto por ocorrência"
(`janela_contexto_regex_loader.py` — continuação da migração)."""

from __future__ import annotations

from batman_os.capabilities.rules.janela_contexto_regex import RegraJanelaSpec
from batman_os.capabilities.rules.janela_contexto_regex_loader import (
    carregar_especificacoes_janela,
)

_TIPOS_DESCOBERTA_VALIDOS = {"arquivo_fixo", "arvore", "glob"}


class TestCarregarEspecificacoesJanela:
    def test_carrega_pelo_menos_5_codigos_distintos(self) -> None:
        specs = carregar_especificacoes_janela()

        codigos = {item["regra"].codigo for item in specs}
        assert len(codigos) >= 5

    def test_toda_regra_e_uma_regrajanelaspec_valida(self) -> None:
        specs = carregar_especificacoes_janela()

        for item in specs:
            assert isinstance(item["regra"], RegraJanelaSpec)
            assert item["regra"].janela_antes >= 0
            assert item["regra"].janela_depois >= 0

    def test_toda_descoberta_tem_tipo_reconhecido(self) -> None:
        specs = carregar_especificacoes_janela()

        for item in specs:
            assert item["descoberta"]["tipo"] in _TIPOS_DESCOBERTA_VALIDOS

    def test_sem_codigos_duplicados(self) -> None:
        specs = carregar_especificacoes_janela()

        codigos = [item["regra"].codigo for item in specs]
        assert len(codigos) == len(set(codigos))
