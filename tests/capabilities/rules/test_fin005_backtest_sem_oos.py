"""Testes do handler bespoke FIN-005 "backtest sem out-of-sample"
(`fin005_backtest_sem_oos.py`)."""

from __future__ import annotations

from batman_os.capabilities.operator import ExecutionContext
from batman_os.capabilities.rules.fin005_backtest_sem_oos import avaliar_fin005
from batman_os.foundation.types import MissionId, StepId, TenantId, agora


def _contexto() -> ExecutionContext:
    return ExecutionContext(
        mission_id=MissionId("m-1"),
        tenant_id=TenantId("t-1"),
        step_id=StepId("s-1"),
        deadline=agora(),
    )


def _regra() -> dict[str, object]:
    return {
        "codigo": "FIN-005",
        "agente": "financial-analyst",
        "severidade": "high",
        "categoria": "validacao",
        "titulo": "titulo",
        "causa": "causa",
        "remediacao": "remediacao",
    }


class TestBacktestSemOos:
    def test_dispara_para_backtest_por_nome_sem_oos(self) -> None:
        entrada = {
            "caminho": "src/backtest_engine.py",
            "conteudo": "def run():\n    pass\n",
            "regra": _regra(),
        }
        saida = avaliar_fin005(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_dispara_para_backtest_por_codigo_sem_oos(self) -> None:
        entrada = {
            "caminho": "src/motor.py",
            "conteudo": "def run_backtest():\n    pass\n",
            "regra": _regra(),
        }
        saida = avaliar_fin005(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_com_walk_forward(self) -> None:
        entrada = {
            "caminho": "src/backtest_engine.py",
            "conteudo": "def run():\n    walk_forward()\n",
            "regra": _regra(),
        }
        saida = avaliar_fin005(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_com_split_train_test(self) -> None:
        entrada = {
            "caminho": "src/backtest_engine.py",
            "conteudo": "def run():\n    train, test = split(dados)\n",
            "regra": _regra(),
        }
        saida = avaliar_fin005(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_sem_gate_de_backtest(self) -> None:
        entrada = {
            "caminho": "src/outra_coisa.py",
            "conteudo": "def run():\n    pass\n",
            "regra": _regra(),
        }
        saida = avaliar_fin005(entrada, _contexto())
        assert saida["achados"] == []
