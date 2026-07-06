"""Testes do loader do spec bespoke ORA-004 (`ora004_loader.py`, Milestone 3)."""

from __future__ import annotations

from batman_os.capabilities.rules.ast_kwarg_ausente_loader import (
    carregar_especificacoes_kwarg_ausente,
)
from batman_os.capabilities.rules.ast_padrao_ausente_loader import carregar_especificacoes_ast
from batman_os.capabilities.rules.de003_loader import carregar_especificacoes_de003
from batman_os.capabilities.rules.execucao_comando_interpretada_loader import (
    carregar_especificacoes_execucao_comando,
)
from batman_os.capabilities.rules.git_comando_interpretado_loader import (
    carregar_especificacoes_git_interpretado,
)
from batman_os.capabilities.rules.lote_01 import carregar_lote_01
from batman_os.capabilities.rules.lote_02 import carregar_lote_02
from batman_os.capabilities.rules.ora004_loader import carregar_especificacoes_ora004
from batman_os.capabilities.rules.ora004_status_typo import RegraOra004Spec
from batman_os.capabilities.rules.ora005_loader import carregar_especificacoes_ora005
from batman_os.capabilities.rules.toml_dependencias_loader import (
    carregar_especificacoes_dependencias,
)


class TestCarregarEspecificacoesOra004:
    def test_carrega_o_codigo_confirmado(self) -> None:
        specs = carregar_especificacoes_ora004()

        codigos = {item["regra"].codigo for item in specs}
        assert codigos == {"ORA-004"}

    def test_toda_regra_e_uma_regraora004spec_valida(self) -> None:
        specs = carregar_especificacoes_ora004()

        for item in specs:
            assert isinstance(item["regra"], RegraOra004Spec)

    def test_toda_descoberta_e_do_tipo_ora004(self) -> None:
        specs = carregar_especificacoes_ora004()

        for item in specs:
            assert item["descoberta"]["tipo"] == "ora004"

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
                + carregar_especificacoes_dependencias()
                + carregar_especificacoes_de003()
                + carregar_especificacoes_ora005()
            )
        }
        codigos_ora004 = {item["regra"].codigo for item in carregar_especificacoes_ora004()}

        assert codigos_outros.isdisjoint(codigos_ora004)
