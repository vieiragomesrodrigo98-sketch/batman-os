"""Testes do loader dos specs da Skill "executar comando externo, timeout,
venv-aware" (`execucao_comando_interpretada_loader.py`, Milestone 3)."""

from __future__ import annotations

from batman_os.capabilities.rules.ast_kwarg_ausente_loader import (
    carregar_especificacoes_kwarg_ausente,
)
from batman_os.capabilities.rules.ast_padrao_ausente_loader import carregar_especificacoes_ast
from batman_os.capabilities.rules.execucao_comando_interpretada import (
    RegraExecucaoComandoSpec,
)
from batman_os.capabilities.rules.execucao_comando_interpretada_loader import (
    carregar_especificacoes_execucao_comando,
)
from batman_os.capabilities.rules.git_comando_interpretado_loader import (
    carregar_especificacoes_git_interpretado,
)
from batman_os.capabilities.rules.lote_01 import carregar_lote_01
from batman_os.capabilities.rules.lote_02 import carregar_lote_02

_CODIGOS_ESPERADOS = {"QA-RUN-001", "QA-RUN-002", "QA-RUN-003", "ORA-001", "ORA-002", "ORA-003"}


class TestCarregarEspecificacoesExecucaoComando:
    def test_carrega_os_6_codigos_confirmados(self) -> None:
        specs = carregar_especificacoes_execucao_comando()

        codigos = {item["regra"].codigo for item in specs}
        assert codigos == _CODIGOS_ESPERADOS

    def test_toda_regra_e_uma_regraexecucaocomandospec_valida(self) -> None:
        specs = carregar_especificacoes_execucao_comando()

        for item in specs:
            assert isinstance(item["regra"], RegraExecucaoComandoSpec)

    def test_toda_descoberta_e_do_tipo_subprocess(self) -> None:
        specs = carregar_especificacoes_execucao_comando()

        for item in specs:
            assert item["descoberta"]["tipo"] == "subprocess"

    def test_nao_repete_nenhum_codigo_ja_migrado(self) -> None:
        codigos_outros = {
            item["regra"].codigo
            for item in (
                carregar_lote_01()
                + carregar_lote_02()
                + carregar_especificacoes_ast()
                + carregar_especificacoes_kwarg_ausente()
                + carregar_especificacoes_git_interpretado()
            )
        }
        codigos_exec = {item["regra"].codigo for item in carregar_especificacoes_execucao_comando()}

        assert codigos_outros.isdisjoint(codigos_exec)
