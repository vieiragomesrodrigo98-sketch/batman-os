"""Testes do handler bespoke CS-005 "resposta de erro sem request_id"
(`cs005_erro_sem_request_id.py`)."""

from __future__ import annotations

import json

from batman_os.capabilities.operator import ExecutionContext
from batman_os.capabilities.rules.cs005_erro_sem_request_id import avaliar_cs005
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
        "codigo": "CS-005",
        "agente": "customer-success",
        "severidade": "medium",
        "categoria": "rastreabilidade",
        "titulo": "titulo",
        "causa": "causa",
        "remediacao": "remediacao",
    }


class TestErroSemRequestId:
    def test_dispara_para_erro_sem_request_id(self) -> None:
        entrada = {
            "caminho": "api/routers/pedidos.py",
            "conteudo": json.dumps(
                {
                    "api_src": "raise HTTPException(status_code=404)\n",
                    "middleware_global_texto": "",
                }
            ),
            "regra": _regra(),
        }
        saida = avaliar_cs005(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_para_erro_com_request_id(self) -> None:
        entrada = {
            "caminho": "api/routers/pedidos.py",
            "conteudo": json.dumps(
                {
                    "api_src": (
                        "raise HTTPException(status_code=404, detail={'request_id': rid})\n"
                    ),
                    "middleware_global_texto": "",
                }
            ),
            "regra": _regra(),
        }
        saida = avaliar_cs005(entrada, _contexto())
        assert saida["achados"] == []

    def test_middleware_global_suprime_a_regra_inteira(self) -> None:
        entrada = {
            "caminho": "api/routers/pedidos.py",
            "conteudo": json.dumps(
                {
                    "api_src": "raise HTTPException(status_code=404)\n",
                    "middleware_global_texto": "def add_request_id(req): pass\n",
                }
            ),
            "regra": _regra(),
        }
        saida = avaliar_cs005(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_sem_padrao_de_erro(self) -> None:
        entrada = {
            "caminho": "api/routers/pedidos.py",
            "conteudo": json.dumps(
                {"api_src": "def listar(): pass\n", "middleware_global_texto": ""}
            ),
            "regra": _regra(),
        }
        saida = avaliar_cs005(entrada, _contexto())
        assert saida["achados"] == []
