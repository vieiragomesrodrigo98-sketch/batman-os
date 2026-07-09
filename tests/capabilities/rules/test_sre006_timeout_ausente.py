"""Testes do handler bespoke SRE-006 "endpoint critico sem timeout de
request" (`sre006_timeout_ausente.py`)."""

from __future__ import annotations

import json

from batman_os.capabilities.operator import ExecutionContext
from batman_os.capabilities.rules.sre006_timeout_ausente import avaliar_sre006
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
        "codigo": "SRE-006",
        "agente": "sre",
        "severidade": "high",
        "categoria": "resiliencia",
        "titulo": "titulo",
        "causa": "causa",
        "remediacao": "remediacao",
    }


class TestTimeoutAusente:
    def test_dispara_para_gunicorn_conf_sem_timeout(self) -> None:
        entrada = {
            "caminho": "gunicorn.conf.py",
            "conteudo": json.dumps({"gunicorn_conf_texto": "workers = 4\n"}),
            "regra": _regra(),
        }
        saida = avaliar_sre006(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_para_gunicorn_conf_com_timeout(self) -> None:
        entrada = {
            "caminho": "gunicorn.conf.py",
            "conteudo": json.dumps({"gunicorn_conf_texto": "timeout = 30\n"}),
            "regra": _regra(),
        }
        saida = avaliar_sre006(entrada, _contexto())
        assert saida["achados"] == []

    def test_dispara_para_script_gunicorn_sem_timeout(self) -> None:
        entrada = {
            "caminho": "scripts",
            "conteudo": json.dumps(
                {"scripts": [["scripts/start.sh", "exec gunicorn app:app -w 4\n"]]}
            ),
            "regra": _regra(),
        }
        saida = avaliar_sre006(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_dispara_para_script_uvicorn_sem_timeout_keep_alive(self) -> None:
        entrada = {
            "caminho": "scripts",
            "conteudo": json.dumps(
                {"scripts": [["scripts/start.sh", "exec uvicorn app:app --host 0.0.0.0\n"]]}
            ),
            "regra": _regra(),
        }
        saida = avaliar_sre006(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_para_script_que_nao_lanca_servidor(self) -> None:
        entrada = {
            "caminho": "scripts",
            "conteudo": json.dumps({"scripts": [["scripts/deploy.sh", "echo ola\n"]]}),
            "regra": _regra(),
        }
        saida = avaliar_sre006(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_sem_conteudo(self) -> None:
        entrada = {"caminho": "gunicorn.conf.py", "conteudo": None, "regra": _regra()}
        saida = avaliar_sre006(entrada, _contexto())
        assert saida["achados"] == []
