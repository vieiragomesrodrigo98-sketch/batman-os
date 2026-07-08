"""Testes do handler bespoke FE-API "rota sem cliente frontend"
(`feapi_rota_sem_frontend.py`)."""

from __future__ import annotations

import json

from batman_os.capabilities.operator import ExecutionContext
from batman_os.capabilities.rules.feapi_rota_sem_frontend import avaliar_feapi
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
        "codigo": "FE-API",
        "agente": "frontend-engineer",
        "severidade": "medium",
        "categoria": "api",
        "titulo": "titulo",
        "causa": "causa",
        "remediacao": "remediacao",
        "caminho_frontend_api": "frontend/src/api",
    }


class TestRotaSemFrontend:
    def test_dispara_quando_rota_nao_aparece_no_frontend(self) -> None:
        entrada = {
            "caminho": "api/routers/pedidos.py",
            "conteudo": json.dumps(
                {
                    "api_src": "@router.get('/pedidos')\ndef listar():\n    pass\n",
                    "frontend_text": "nada relacionado aqui",
                }
            ),
            "regra": _regra(),
        }
        saida = avaliar_feapi(entrada, _contexto())
        assert len(saida["achados"]) == 1
        assert saida["achados"][0]["chave"] == "/pedidos"

    def test_nao_dispara_quando_rota_aparece_no_frontend(self) -> None:
        entrada = {
            "caminho": "api/routers/pedidos.py",
            "conteudo": json.dumps(
                {
                    "api_src": "@router.get('/pedidos')\ndef listar():\n    pass\n",
                    "frontend_text": "fetch('/pedidos')",
                }
            ),
            "regra": _regra(),
        }
        saida = avaliar_feapi(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_para_prefixo_admin(self) -> None:
        entrada = {
            "caminho": "api/routers/interno.py",
            "conteudo": json.dumps(
                {
                    "api_src": "@router.get('/admin/usuarios')\ndef listar():\n    pass\n",
                    "frontend_text": "",
                }
            ),
            "regra": _regra(),
        }
        saida = avaliar_feapi(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_para_arquivo_admin_router(self) -> None:
        entrada = {
            "caminho": "api/routers/admin.py",
            "conteudo": json.dumps(
                {
                    "api_src": "@router.get('/qualquer')\ndef listar():\n    pass\n",
                    "frontend_text": "",
                }
            ),
            "regra": _regra(),
        }
        saida = avaliar_feapi(entrada, _contexto())
        assert saida["achados"] == []

    def test_multiplas_rotas_produzem_multiplos_achados_com_chaves_distintas(self) -> None:
        entrada = {
            "caminho": "api/routers/pedidos.py",
            "conteudo": json.dumps(
                {
                    "api_src": (
                        "@router.get('/pedidos')\n"
                        "def listar():\n"
                        "    pass\n"
                        "@router.get('/pedidos/resumo')\n"
                        "def resumo():\n"
                        "    pass\n"
                    ),
                    "frontend_text": "nada relacionado aqui",
                }
            ),
            "regra": _regra(),
        }
        saida = avaliar_feapi(entrada, _contexto())
        assert len(saida["achados"]) == 2
        chaves = {a["chave"] for a in saida["achados"]}
        assert chaves == {"/pedidos", "/pedidos/resumo"}
