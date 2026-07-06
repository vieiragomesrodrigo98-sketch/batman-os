"""Testes do loader do segundo lote de migração (`capabilities/rules/lote_02.py`,
Milestone 2 — migração mecânica em massa)."""

from __future__ import annotations

from batman_os.capabilities.rules.lote_01 import carregar_lote_01
from batman_os.capabilities.rules.lote_02 import carregar_lote_02
from batman_os.capabilities.rules.regex_sobre_conteudo import ModoAvaliacao, RegraSpec

_TIPOS_DESCOBERTA_VALIDOS = {"arquivo_fixo", "arvore", "glob"}


class TestCarregarLote02:
    def test_carrega_um_volume_significativo_de_regras(self) -> None:
        lote = carregar_lote_02()

        assert len(lote) >= 150

    def test_toda_regra_e_uma_regraspec_valida(self) -> None:
        lote = carregar_lote_02()

        for item in lote:
            assert isinstance(item["regra"], RegraSpec)
            assert item["regra"].modo in ModoAvaliacao

    def test_toda_descoberta_tem_tipo_reconhecido(self) -> None:
        lote = carregar_lote_02()

        for item in lote:
            assert item["descoberta"]["tipo"] in _TIPOS_DESCOBERTA_VALIDOS

    def test_sem_codigos_duplicados_dentro_do_lote(self) -> None:
        lote = carregar_lote_02()

        codigos = [item["regra"].codigo for item in lote]
        assert len(codigos) == len(set(codigos))

    def test_nao_repete_nenhum_codigo_ja_migrado_no_lote_01(self) -> None:
        codigos_lote_01 = {item["regra"].codigo for item in carregar_lote_01()}
        codigos_lote_02 = {item["regra"].codigo for item in carregar_lote_02()}

        assert codigos_lote_01.isdisjoint(codigos_lote_02)
