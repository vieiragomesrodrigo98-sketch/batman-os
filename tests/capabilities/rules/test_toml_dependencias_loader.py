"""Testes do loader dos specs da Skill "parsing TOML real de pyproject.toml"
(`toml_dependencias_loader.py`, Milestone 3)."""

from __future__ import annotations

from batman_os.capabilities.rules.ast_kwarg_ausente_loader import (
    carregar_especificacoes_kwarg_ausente,
)
from batman_os.capabilities.rules.ast_padrao_ausente_loader import carregar_especificacoes_ast
from batman_os.capabilities.rules.execucao_comando_interpretada_loader import (
    carregar_especificacoes_execucao_comando,
)
from batman_os.capabilities.rules.git_comando_interpretado_loader import (
    carregar_especificacoes_git_interpretado,
)
from batman_os.capabilities.rules.lote_01 import carregar_lote_01
from batman_os.capabilities.rules.lote_02 import carregar_lote_02
from batman_os.capabilities.rules.toml_dependencias import RegraDependenciasSpec
from batman_os.capabilities.rules.toml_dependencias_loader import (
    carregar_especificacoes_dependencias,
)

_CODIGOS_ESPERADOS = {"DEP-001", "DEP-002", "DEP-003", "DEP-004"}


class TestCarregarEspecificacoesDependencias:
    def test_carrega_os_4_codigos_confirmados(self) -> None:
        specs = carregar_especificacoes_dependencias()

        codigos = {item["regra"].codigo for item in specs}
        assert codigos == _CODIGOS_ESPERADOS

    def test_toda_regra_e_uma_regradependenciasspec_valida(self) -> None:
        specs = carregar_especificacoes_dependencias()

        for item in specs:
            assert isinstance(item["regra"], RegraDependenciasSpec)

    def test_toda_descoberta_e_do_tipo_toml_dependencias(self) -> None:
        specs = carregar_especificacoes_dependencias()

        for item in specs:
            assert item["descoberta"]["tipo"] == "toml_dependencias"

    def test_nao_repete_nenhum_codigo_ja_migrado(self) -> None:
        codigos_outros = {
            item["regra"].codigo
            for item in (
                carregar_lote_01()
                + carregar_lote_02()
                + carregar_especificacoes_ast()
                + carregar_especificacoes_kwarg_ausente()
                + carregar_especificacoes_git_interpretado()
                + carregar_especificacoes_execucao_comando()
            )
        }
        codigos_dep = {item["regra"].codigo for item in carregar_especificacoes_dependencias()}

        assert codigos_outros.isdisjoint(codigos_dep)
