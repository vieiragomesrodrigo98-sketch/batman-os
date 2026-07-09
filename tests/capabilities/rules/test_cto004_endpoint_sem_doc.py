"""Testes do handler bespoke CTO-004 "endpoint sem docstring nem
response_model" (`cto004_endpoint_sem_doc.py`)."""

from __future__ import annotations

from batman_os.capabilities.operator import ExecutionContext
from batman_os.capabilities.rules.cto004_endpoint_sem_doc import avaliar_cto004
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
        "codigo": "CTO-004",
        "agente": "cto",
        "severidade": "low",
        "categoria": "api-design",
        "titulo": "titulo",
        "causa": "causa",
        "remediacao": "remediacao",
    }


class TestEndpointSemDoc:
    def test_dispara_para_endpoint_sem_docstring_nem_response_model(self) -> None:
        entrada = {
            "caminho": "api/routers/pedidos.py",
            "conteudo": "@router.get('/pedidos')\ndef listar():\n    return []\n",
            "regra": _regra(),
        }
        saida = avaliar_cto004(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_com_docstring(self) -> None:
        entrada = {
            "caminho": "api/routers/pedidos.py",
            "conteudo": (
                "@router.get('/pedidos')\ndef listar():\n"
                '    """Lista pedidos."""\n    return []\n'
            ),
            "regra": _regra(),
        }
        saida = avaliar_cto004(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_com_response_model_no_decorator(self) -> None:
        entrada = {
            "caminho": "api/routers/pedidos.py",
            "conteudo": (
                "@router.get('/pedidos', response_model=list[Pedido])\n"
                "def listar():\n    return []\n"
            ),
            "regra": _regra(),
        }
        saida = avaliar_cto004(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_sem_decorator_de_rota(self) -> None:
        entrada = {
            "caminho": "api/routers/pedidos.py",
            "conteudo": "def helper():\n    return []\n",
            "regra": _regra(),
        }
        saida = avaliar_cto004(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_sem_conteudo(self) -> None:
        entrada = {"caminho": "api/routers/x.py", "conteudo": None, "regra": _regra()}
        saida = avaliar_cto004(entrada, _contexto())
        assert saida["achados"] == []
