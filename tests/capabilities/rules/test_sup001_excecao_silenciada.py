"""Testes do handler bespoke SUP-001 "exceção silenciada"
(`sup001_excecao_silenciada.py`)."""

from __future__ import annotations

from batman_os.capabilities.operator import ExecutionContext
from batman_os.capabilities.rules.sup001_excecao_silenciada import avaliar_sup001
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
        "codigo": "SUP-001",
        "agente": "support",
        "severidade": "medium",
        "categoria": "tratamento-de-erros",
        "titulo": "titulo",
        "causa": "causa",
        "remediacao": "remediacao",
    }


class TestExcecaoSilenciada:
    def test_dispara_com_except_pass(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": "try:\n    x()\nexcept Exception:\n    pass\n",
            "regra": _regra(),
        }
        saida = avaliar_sup001(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_com_log(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": "try:\n    x()\nexcept Exception:\n    logger.exception('falhou')\n",
            "regra": _regra(),
        }
        saida = avaliar_sup001(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_com_reraise(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": "try:\n    x()\nexcept Exception:\n    raise\n",
            "regra": _regra(),
        }
        saida = avaliar_sup001(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_para_excecao_da_safelist(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": "try:\n    import optional_dep\nexcept ImportError:\n    pass\n",
            "regra": _regra(),
        }
        saida = avaliar_sup001(entrada, _contexto())
        assert saida["achados"] == []

    def test_dispara_para_excecao_fora_da_safelist_mesmo_com_pass_isolado(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": "try:\n    x()\nexcept ValueError:\n    pass\n",
            "regra": _regra(),
        }
        saida = avaliar_sup001(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_quando_excecao_e_guardada_para_re_raise_posterior(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": (
                "try:\n    x()\nexcept Exception as exc:\n    ultimo_erro = exc\n    continue\n"
            ),
            "regra": _regra(),
        }
        saida = avaliar_sup001(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_com_erro_de_sintaxe(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": "def (:\n",
            "regra": _regra(),
        }
        saida = avaliar_sup001(entrada, _contexto())
        assert saida["achados"] == []
