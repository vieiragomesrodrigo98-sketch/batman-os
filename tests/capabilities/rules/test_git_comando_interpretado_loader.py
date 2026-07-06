"""Testes do loader dos specs da Skill "comando git único interpretado"
(`git_comando_interpretado_loader.py`, Milestone 3)."""

from __future__ import annotations

from batman_os.capabilities.rules.ast_kwarg_ausente_loader import (
    carregar_especificacoes_kwarg_ausente,
)
from batman_os.capabilities.rules.ast_padrao_ausente_loader import carregar_especificacoes_ast
from batman_os.capabilities.rules.git_comando_interpretado import RegraComparacaoNumericaSpec
from batman_os.capabilities.rules.git_comando_interpretado_loader import (
    carregar_especificacoes_git_interpretado,
)
from batman_os.capabilities.rules.lote_01 import carregar_lote_01
from batman_os.capabilities.rules.lote_02 import carregar_lote_02

_CODIGOS_ESPERADOS = {"QA-008"}


class TestCarregarEspecificacoesGitInterpretado:
    def test_carrega_o_codigo_confirmado(self) -> None:
        specs = carregar_especificacoes_git_interpretado()

        codigos = {item["regra"].codigo for item in specs}
        assert codigos == _CODIGOS_ESPERADOS

    def test_toda_regra_e_uma_regracomparacaonumericaspec_valida(self) -> None:
        specs = carregar_especificacoes_git_interpretado()

        for item in specs:
            assert isinstance(item["regra"], RegraComparacaoNumericaSpec)

    def test_toda_descoberta_e_do_tipo_git(self) -> None:
        specs = carregar_especificacoes_git_interpretado()

        for item in specs:
            assert item["descoberta"]["tipo"] == "git"

    def test_nao_repete_nenhum_codigo_ja_migrado(self) -> None:
        codigos_outros = {
            item["regra"].codigo
            for item in (
                carregar_lote_01()
                + carregar_lote_02()
                + carregar_especificacoes_ast()
                + carregar_especificacoes_kwarg_ausente()
            )
        }
        codigos_git = {item["regra"].codigo for item in carregar_especificacoes_git_interpretado()}

        assert codigos_outros.isdisjoint(codigos_git)
