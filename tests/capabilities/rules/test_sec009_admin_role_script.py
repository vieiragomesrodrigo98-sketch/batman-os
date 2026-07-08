"""Testes do handler bespoke SEC-009 "script cria admin/super_admin via
SQL direto ou ORM fora da API" (`sec009_admin_role_script.py`)."""

from __future__ import annotations

from batman_os.capabilities.operator import ExecutionContext
from batman_os.capabilities.rules.sec009_admin_role_script import avaliar_sec009
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
        "codigo": "SEC-009",
        "agente": "security-engineer",
        "severidade": "high",
        "categoria": "access-control",
        "titulo": "titulo",
        "causa": "causa",
        "remediacao": "remediacao",
    }


class TestAdminRoleScript:
    def test_dispara_para_insert_sql_com_role_admin(self) -> None:
        entrada = {
            "caminho": "scripts/promote_user.py",
            "conteudo": (
                "conn = sqlite3.connect('x.db')\n"
                "conn.execute(\"INSERT INTO users (role) VALUES ('admin')\")\n"
            ),
            "regra": _regra(),
        }
        saida = avaliar_sec009(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_dispara_para_atribuicao_orm_de_role(self) -> None:
        entrada = {
            "caminho": "scripts/promote_user.py",
            "conteudo": ("session = Session()\nuser.role = 'super_admin'\n"),
            "regra": _regra(),
        }
        saida = avaliar_sec009(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_sem_uso_de_banco(self) -> None:
        entrada = {
            "caminho": "scripts/algo.py",
            "conteudo": "print('INSERT INTO users role admin')\n",
            "regra": _regra(),
        }
        saida = avaliar_sec009(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_para_create_prod_users(self) -> None:
        entrada = {
            "caminho": "scripts/create_prod_users.py",
            "conteudo": (
                "conn = sqlite3.connect('x.db')\n"
                "conn.execute(\"INSERT INTO users (role) VALUES ('admin')\")\n"
            ),
            "regra": _regra(),
        }
        saida = avaliar_sec009(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_para_insert_sem_role_admin(self) -> None:
        entrada = {
            "caminho": "scripts/promote_user.py",
            "conteudo": (
                "conn = sqlite3.connect('x.db')\n"
                "conn.execute(\"INSERT INTO logs (msg) VALUES ('x')\")\n"
            ),
            "regra": _regra(),
        }
        saida = avaliar_sec009(entrada, _contexto())
        assert saida["achados"] == []
