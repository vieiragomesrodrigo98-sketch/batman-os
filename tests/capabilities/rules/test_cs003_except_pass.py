"""Testes do handler bespoke CS-003 "except com pass silencia exceção"
(`cs003_except_pass.py`)."""

from __future__ import annotations

from batman_os.capabilities.operator import ExecutionContext
from batman_os.capabilities.rules.cs003_except_pass import avaliar_cs003
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
        "codigo": "CS-003",
        "agente": "customer-success",
        "severidade": "medium",
        "categoria": "estabilidade",
        "titulo": "titulo",
        "causa": "causa",
        "remediacao": "remediacao",
    }


class TestExceptComPass:
    def test_dispara_para_except_com_pass_exato(self) -> None:
        entrada = {
            "caminho": "api/x.py",
            "conteudo": "try:\n    f()\nexcept Exception:\n    pass\n",
            "regra": _regra(),
        }
        saida = avaliar_cs003(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_para_except_com_tratamento(self) -> None:
        entrada = {
            "caminho": "api/x.py",
            "conteudo": "try:\n    f()\nexcept Exception as e:\n    log.error(e)\n    raise\n",
            "regra": _regra(),
        }
        saida = avaliar_cs003(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_para_except_com_pass_mais_outra_instrucao(self) -> None:
        entrada = {
            "caminho": "api/x.py",
            "conteudo": "try:\n    f()\nexcept Exception:\n    pass\n    log.info('x')\n",
            "regra": _regra(),
        }
        saida = avaliar_cs003(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_sem_erro_de_sintaxe_gera_vazio(self) -> None:
        entrada = {"caminho": "api/x.py", "conteudo": "def (:\n", "regra": _regra()}
        saida = avaliar_cs003(entrada, _contexto())
        assert saida["achados"] == []
