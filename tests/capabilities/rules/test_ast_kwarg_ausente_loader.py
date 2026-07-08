"""Testes do loader dos specs da Skill AST "Call com kwarg obrigatório
ausente" (`ast_kwarg_ausente_loader.py`, Milestone 3)."""

from __future__ import annotations

from batman_os.capabilities.rules.ast_kwarg_ausente import RegraKwargAusenteSpec
from batman_os.capabilities.rules.ast_kwarg_ausente_loader import (
    carregar_especificacoes_kwarg_ausente,
)
from batman_os.capabilities.rules.ast_padrao_ausente_loader import carregar_especificacoes_ast
from batman_os.capabilities.rules.lote_01 import carregar_lote_01
from batman_os.capabilities.rules.lote_02 import carregar_lote_02

_TIPOS_DESCOBERTA_VALIDOS = {"arquivo_fixo", "arvore", "glob"}
_CODIGOS_ESPERADOS = {"CTO-001", "CS-001"}


class TestCarregarEspecificacoesKwargAusente:
    def test_carrega_o_codigo_confirmado(self) -> None:
        specs = carregar_especificacoes_kwarg_ausente()

        codigos = {item["regra"].codigo for item in specs}
        assert codigos == _CODIGOS_ESPERADOS

    def test_toda_regra_e_uma_regrakwargausentespec_valida(self) -> None:
        specs = carregar_especificacoes_kwarg_ausente()

        for item in specs:
            assert isinstance(item["regra"], RegraKwargAusenteSpec)

    def test_toda_descoberta_tem_tipo_reconhecido(self) -> None:
        specs = carregar_especificacoes_kwarg_ausente()

        for item in specs:
            assert item["descoberta"]["tipo"] in _TIPOS_DESCOBERTA_VALIDOS

    def test_nao_repete_nenhum_codigo_ja_migrado(self) -> None:
        codigos_outros = {
            item["regra"].codigo
            for item in carregar_lote_01() + carregar_lote_02() + carregar_especificacoes_ast()
        }
        codigos_kwarg = {item["regra"].codigo for item in carregar_especificacoes_kwarg_ausente()}

        assert codigos_outros.isdisjoint(codigos_kwarg)
