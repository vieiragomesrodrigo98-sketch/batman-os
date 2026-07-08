"""Testes do loader do terceiro lote de migração
(`capabilities/rules/lote_03.py` — continuação da migração além do escopo
original de Milestones 1-3)."""

from __future__ import annotations

from batman_os.capabilities.rules.lote_01 import carregar_lote_01
from batman_os.capabilities.rules.lote_02 import carregar_lote_02
from batman_os.capabilities.rules.lote_03 import carregar_lote_03
from batman_os.capabilities.rules.regex_sobre_conteudo import ModoAvaliacao, RegraSpec

_TIPOS_DESCOBERTA_VALIDOS = {"arquivo_fixo", "arvore", "glob"}

# NS-003, MOB-002, MOB-003 e A11Y-007 têm múltiplas entradas (fontes/caminhos
# distintos para o mesmo código, replicando o legado) — código legítimo
# repetido.
_CODIGOS_COM_MULTIPLAS_ENTRADAS = {"NS-003", "MOB-002", "MOB-003", "A11Y-007"}


class TestCarregarLote03:
    def test_carrega_pelo_menos_7_codigos_distintos(self) -> None:
        lote = carregar_lote_03()

        codigos = {item["regra"].codigo for item in lote}
        assert len(codigos) >= 7

    def test_toda_regra_e_uma_regraspec_valida(self) -> None:
        lote = carregar_lote_03()

        for item in lote:
            assert isinstance(item["regra"], RegraSpec)
            assert item["regra"].modo in ModoAvaliacao

    def test_toda_descoberta_tem_tipo_reconhecido(self) -> None:
        lote = carregar_lote_03()

        for item in lote:
            assert item["descoberta"]["tipo"] in _TIPOS_DESCOBERTA_VALIDOS

    def test_codigos_repetidos_dentro_do_lote_sao_so_os_esperados(self) -> None:
        lote = carregar_lote_03()

        codigos = [item["regra"].codigo for item in lote]
        repetidos = {c for c in codigos if codigos.count(c) > 1}
        assert repetidos == _CODIGOS_COM_MULTIPLAS_ENTRADAS

    def test_nao_repete_nenhum_codigo_ja_migrado_nos_lotes_anteriores(self) -> None:
        codigos_anteriores = {item["regra"].codigo for item in carregar_lote_01()} | {
            item["regra"].codigo for item in carregar_lote_02()
        }
        codigos_lote_03 = {item["regra"].codigo for item in carregar_lote_03()}

        assert codigos_anteriores.isdisjoint(codigos_lote_03)
