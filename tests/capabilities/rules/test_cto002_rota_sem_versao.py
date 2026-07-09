"""Testes do handler bespoke CTO-002 "rota de API sem prefixo de versão"
(`cto002_rota_sem_versao.py`)."""

from __future__ import annotations

from batman_os.capabilities.operator import ExecutionContext
from batman_os.capabilities.rules.cto002_rota_sem_versao import avaliar_cto002
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
        "codigo": "CTO-002",
        "agente": "cto",
        "severidade": "medium",
        "categoria": "api-design",
        "titulo": "titulo",
        "causa": "causa",
        "remediacao": "remediacao",
    }


class TestRotaSemVersao:
    def test_dispara_para_rota_sem_prefixo_de_versao(self) -> None:
        entrada = {
            "caminho": "api/routers/pedidos.py",
            "conteudo": "@router.get('/pedidos')\ndef listar():\n    pass\n",
            "regra": _regra(),
        }
        saida = avaliar_cto002(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_para_rota_com_prefixo_de_versao(self) -> None:
        entrada = {
            "caminho": "api/routers/pedidos.py",
            "conteudo": "@router.get('/v1/pedidos')\ndef listar():\n    pass\n",
            "regra": _regra(),
        }
        saida = avaliar_cto002(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_para_rotas_de_excecao(self) -> None:
        entrada = {
            "caminho": "api/routers/health.py",
            "conteudo": "@router.get('/health')\ndef health():\n    pass\n",
            "regra": _regra(),
        }
        saida = avaliar_cto002(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_para_erro_de_sintaxe(self) -> None:
        entrada = {"caminho": "api/routers/x.py", "conteudo": "def (:\n", "regra": _regra()}
        saida = avaliar_cto002(entrada, _contexto())
        assert saida["achados"] == []
