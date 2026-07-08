"""Testes do handler bespoke BA-005 "divisão sem guarda contra zero"
(`ba005_divisao_sem_guarda.py`)."""

from __future__ import annotations

from batman_os.capabilities.operator import ExecutionContext
from batman_os.capabilities.rules.ba005_divisao_sem_guarda import avaliar_ba005
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
        "codigo": "BA-005",
        "agente": "business-analyst",
        "severidade": "high",
        "categoria": "financeiro",
        "titulo": "titulo",
        "causa": "causa",
        "remediacao": "remediacao",
    }


class TestDivisaoSemGuarda:
    def test_dispara_em_modulo_financeiro_sem_guarda(self) -> None:
        entrada = {
            "caminho": "src/radar/engines/risk_engine.py",
            "conteudo": "def calc(total, count):\n    return total / count\n",
            "regra": _regra(),
        }
        saida = avaliar_ba005(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_fora_do_escopo_de_palavras_chave(self) -> None:
        entrada = {
            "caminho": "src/radar/utils/helpers.py",
            "conteudo": "def calc(total, count):\n    return total / count\n",
            "regra": _regra(),
        }
        saida = avaliar_ba005(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_com_guarda_no_arquivo(self) -> None:
        entrada = {
            "caminho": "src/radar/engines/risk_engine.py",
            "conteudo": (
                "def calc(total, count):\n"
                "    if count != 0:\n"
                "        return total / count\n"
                "    return 0\n"
            ),
            "regra": _regra(),
        }
        saida = avaliar_ba005(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_para_divisao_por_literal(self) -> None:
        entrada = {
            "caminho": "src/radar/engines/risk_engine.py",
            "conteudo": "def calc(total):\n    return total / 100\n",
            "regra": _regra(),
        }
        saida = avaliar_ba005(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_para_divisao_dentro_de_docstring(self) -> None:
        entrada = {
            "caminho": "src/radar/engines/risk_engine.py",
            "conteudo": (
                "def calc(total, count):\n"
                '    """\n'
                "    exemplo: total / count\n"
                '    """\n'
                "    return 0\n"
            ),
            "regra": _regra(),
        }
        saida = avaliar_ba005(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_para_floor_division(self) -> None:
        entrada = {
            "caminho": "src/radar/engines/risk_engine.py",
            "conteudo": "def calc(total, count):\n    return total // count\n",
            "regra": _regra(),
        }
        saida = avaliar_ba005(entrada, _contexto())
        assert saida["achados"] == []
