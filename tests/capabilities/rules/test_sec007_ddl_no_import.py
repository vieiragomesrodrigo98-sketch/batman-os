"""Testes do handler bespoke SEC-007 "DDL no import do módulo"
(`sec007_ddl_no_import.py`)."""

from __future__ import annotations

from batman_os.capabilities.operator import ExecutionContext
from batman_os.capabilities.rules.sec007_ddl_no_import import avaliar_sec007
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
        "codigo": "SEC-007",
        "agente": "security-engineer",
        "severidade": "medium",
        "categoria": "data",
        "titulo": "titulo",
        "causa": "causa",
        "remediacao": "remediacao",
    }


class TestDdlNoImport:
    def test_dispara_com_create_table_no_nivel_do_modulo(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": 'conn.execute("CREATE TABLE x (id int)")\n',
            "regra": _regra(),
        }
        saida = avaliar_sec007(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_dispara_com_run_migrations_no_nivel_do_modulo(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": "run_migrations()\n",
            "regra": _regra(),
        }
        saida = avaliar_sec007(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_quando_ddl_esta_dentro_de_funcao(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": "def init():\n    conn.execute('CREATE TABLE x (id int)')\n",
            "regra": _regra(),
        }
        saida = avaliar_sec007(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_sem_ddl(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": "print('oi')\n",
            "regra": _regra(),
        }
        saida = avaliar_sec007(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_com_erro_de_sintaxe(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": "def (:\n",
            "regra": _regra(),
        }
        saida = avaliar_sec007(entrada, _contexto())
        assert saida["achados"] == []
