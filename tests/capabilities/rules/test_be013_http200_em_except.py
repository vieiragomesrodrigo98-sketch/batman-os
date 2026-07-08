"""Testes do handler bespoke BE-013 "HTTP 200 em bloco except"
(`be013_http200_em_except.py`)."""

from __future__ import annotations

from batman_os.capabilities.operator import ExecutionContext
from batman_os.capabilities.rules.be013_http200_em_except import avaliar_be013
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
        "codigo": "BE-013",
        "agente": "backend-engineer",
        "severidade": "high",
        "categoria": "api",
        "titulo": "titulo",
        "causa": "causa",
        "remediacao": "remediacao",
    }


class TestHttp200EmExcept:
    def test_dispara_com_status_200_dentro_do_except(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": (
                "try:\n"
                "    fazer_algo()\n"
                "except Exception:\n"
                "    return JSONResponse(status_code=200, content={'erro': True})\n"
            ),
            "regra": _regra(),
        }
        saida = avaliar_be013(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_apos_dedent_do_except(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": (
                "try:\n"
                "    fazer_algo()\n"
                "except Exception:\n"
                "    return JSONResponse(status_code=500)\n"
                "return JSONResponse(status_code=200)\n"
            ),
            "regra": _regra(),
        }
        saida = avaliar_be013(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_com_status_500_no_except(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": (
                "try:\n    fazer_algo()\nexcept Exception:\n"
                "    return JSONResponse(status_code=500)\n"
            ),
            "regra": _regra(),
        }
        saida = avaliar_be013(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_sem_except_no_arquivo(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": "return JSONResponse(status_code=200)\n",
            "regra": _regra(),
        }
        saida = avaliar_be013(entrada, _contexto())
        assert saida["achados"] == []

    def test_comentario_dedentado_ao_nivel_do_except_nao_encerra_o_bloco(self) -> None:
        # Comentario na mesma indentacao do 'except' (dedent) nao conta como
        # saida do bloco (replica legado: `not stripped.startswith("#")`).
        entrada = {
            "caminho": "a.py",
            "conteudo": (
                "try:\n"
                "    fazer_algo()\n"
                "except Exception:\n"
                "    x = 1\n"
                "# comentario dedentado ao nivel do except\n"
                "    return JSONResponse(status_code=200)\n"
            ),
            "regra": _regra(),
        }
        saida = avaliar_be013(entrada, _contexto())
        assert len(saida["achados"]) == 1
