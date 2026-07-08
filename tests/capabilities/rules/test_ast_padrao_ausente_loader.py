"""Testes do loader dos specs da Skill AST (`ast_padrao_ausente_loader.py`,
Milestone 3 + continuação da migração)."""

from __future__ import annotations

from batman_os.capabilities.rules.ast_padrao_ausente import RegraAstSpec, SeletorTipo
from batman_os.capabilities.rules.ast_padrao_ausente_loader import carregar_especificacoes_ast
from batman_os.capabilities.rules.lote_01 import carregar_lote_01
from batman_os.capabilities.rules.lote_02 import carregar_lote_02

_TIPOS_DESCOBERTA_VALIDOS = {"arquivo_fixo", "arvore", "glob"}
_CODIGOS_ESPERADOS = {
    "BT-001",
    "BT-002",
    "BT-003",
    "COMP-001",
    "COMP-002",
    "EH-004",
    "EH-006",
    "DE-006",
    "RISK-002",
}


class TestCarregarEspecificacoesAst:
    def test_carrega_os_codigos_confirmados(self) -> None:
        specs = carregar_especificacoes_ast()

        codigos = {item["regra"].codigo for item in specs}
        assert codigos == _CODIGOS_ESPERADOS

    def test_toda_regra_e_uma_regraastspec_valida(self) -> None:
        specs = carregar_especificacoes_ast()

        for item in specs:
            assert isinstance(item["regra"], RegraAstSpec)
            assert item["regra"].seletor_tipo in SeletorTipo

    def test_toda_descoberta_tem_tipo_reconhecido(self) -> None:
        specs = carregar_especificacoes_ast()

        for item in specs:
            assert item["descoberta"]["tipo"] in _TIPOS_DESCOBERTA_VALIDOS

    def test_sem_codigos_duplicados(self) -> None:
        specs = carregar_especificacoes_ast()

        codigos = [item["regra"].codigo for item in specs]
        assert len(codigos) == len(set(codigos))

    def test_nao_repete_nenhum_codigo_ja_migrado_nos_lotes_regex(self) -> None:
        codigos_regex = {item["regra"].codigo for item in carregar_lote_01() + carregar_lote_02()}
        codigos_ast = {item["regra"].codigo for item in carregar_especificacoes_ast()}

        assert codigos_regex.isdisjoint(codigos_ast)
