"""Testes do loader do spec bespoke ORA-005 (`ora005_loader.py`, Milestone 3)."""

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
from batman_os.capabilities.rules.ora005_fallback_silencioso import RegraOra005Spec
from batman_os.capabilities.rules.ora005_loader import carregar_especificacoes_ora005
from batman_os.capabilities.rules.toml_dependencias_loader import (
    carregar_especificacoes_dependencias,
)


class TestCarregarEspecificacoesOra005:
    def test_carrega_o_codigo_confirmado(self) -> None:
        specs = carregar_especificacoes_ora005()

        codigos = {item["regra"].codigo for item in specs}
        assert codigos == {"ORA-005"}

    def test_toda_regra_e_uma_regraora005spec_valida(self) -> None:
        specs = carregar_especificacoes_ora005()

        for item in specs:
            assert isinstance(item["regra"], RegraOra005Spec)

    def test_toda_descoberta_e_do_tipo_arvore(self) -> None:
        specs = carregar_especificacoes_ora005()

        for item in specs:
            assert item["descoberta"]["tipo"] == "arvore"

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
            )
        }
        codigos_ora005 = {item["regra"].codigo for item in carregar_especificacoes_ora005()}

        assert codigos_outros.isdisjoint(codigos_ora005)
