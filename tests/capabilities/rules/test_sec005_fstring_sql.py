"""Testes do handler bespoke SEC-005 "SQL com f-string"
(`sec005_fstring_sql.py`)."""

from __future__ import annotations

from batman_os.capabilities.operator import ExecutionContext
from batman_os.capabilities.rules.sec005_fstring_sql import avaliar_sec005
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
        "codigo": "SEC-005",
        "agente": "security-engineer",
        "severidade": "medium",
        "categoria": "sql",
        "titulo": "titulo",
        "causa": "causa",
        "remediacao": "remediacao",
    }


class TestSqlComFstring:
    def test_dispara_com_execute_fstring(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": 'cursor.execute(f"SELECT * FROM t WHERE id={id}")\n',
            "regra": _regra(),
        }
        saida = avaliar_sec005(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_com_execute_parametrizado(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": "cursor.execute('SELECT * FROM t WHERE id=%s', (id,))\n",
            "regra": _regra(),
        }
        saida = avaliar_sec005(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_para_call_de_outro_metodo_com_fstring(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": 'logger.info(f"processando {id}")\n',
            "regra": _regra(),
        }
        saida = avaliar_sec005(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_com_erro_de_sintaxe(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": "def (:\n",
            "regra": _regra(),
        }
        saida = avaliar_sec005(entrada, _contexto())
        assert saida["achados"] == []
