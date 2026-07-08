"""Testes do handler bespoke BA-004 "lógica de negócio no router"
(`ba004_logica_negocio_router.py`)."""

from __future__ import annotations

from batman_os.capabilities.operator import ExecutionContext
from batman_os.capabilities.rules.ba004_logica_negocio_router import avaliar_ba004
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
        "codigo": "BA-004",
        "agente": "business-analyst",
        "severidade": "medium",
        "categoria": "arquitetura",
        "titulo": "titulo",
        "causa": "causa",
        "remediacao": "remediacao",
    }


class TestLogicaNegocioRouter:
    def test_dispara_com_3_operacoes_aritmeticas_em_rota(self) -> None:
        entrada = {
            "caminho": "api/routers/x.py",
            "conteudo": (
                "@router.get('/calc')\n"
                "def calc(a: int, b: int, c: int):\n"
                "    x = a * b\n"
                "    y = b / c\n"
                "    z = a % c\n"
                "    return x + y + z\n"
            ),
            "regra": _regra(),
        }
        saida = avaliar_ba004(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_com_apenas_2_operacoes(self) -> None:
        entrada = {
            "caminho": "api/routers/x.py",
            "conteudo": (
                "@router.get('/calc')\ndef calc(a: int, b: int):\n    x = a * b\n    return x\n"
            ),
            "regra": _regra(),
        }
        saida = avaliar_ba004(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_quando_arquivo_usa_camada_de_servico(self) -> None:
        entrada = {
            "caminho": "api/routers/y.py",
            "conteudo": (
                "@router.get('/calc')\ndef calc(a: int, b: int, c: int):\n"
                "    return service.compute(a, b, c)\n"
            ),
            "regra": _regra(),
        }
        saida = avaliar_ba004(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_para_operacoes_fora_de_uma_rota(self) -> None:
        entrada = {
            "caminho": "api/routers/z.py",
            "conteudo": (
                "def helper(a: int, b: int, c: int):\n"
                "    x = a * b\n"
                "    y = b / c\n"
                "    z = a % c\n"
                "    return x + y + z\n"
            ),
            "regra": _regra(),
        }
        saida = avaliar_ba004(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_para_divisao_estilo_path(self) -> None:
        entrada = {
            "caminho": "api/routers/w.py",
            "conteudo": (
                "@router.get('/calc')\n"
                "def calc(base):\n"
                "    p1 = base / 'a'\n"
                "    p2 = base / 'b'\n"
                "    p3 = base / 'c'\n"
                "    return p1, p2, p3\n"
            ),
            "regra": _regra(),
        }
        saida = avaliar_ba004(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_com_erro_de_sintaxe(self) -> None:
        entrada = {
            "caminho": "api/routers/v.py",
            "conteudo": "def (:\n",
            "regra": _regra(),
        }
        saida = avaliar_ba004(entrada, _contexto())
        assert saida["achados"] == []
