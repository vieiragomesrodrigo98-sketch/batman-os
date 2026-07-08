"""Testes do handler bespoke REV-006 "nome de variável com 1–2
caracteres" (`rev006_variavel_nome_curto.py`)."""

from __future__ import annotations

from batman_os.capabilities.operator import ExecutionContext
from batman_os.capabilities.rules.rev006_variavel_nome_curto import avaliar_rev006
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
        "codigo": "REV-006",
        "agente": "code-reviewer",
        "severidade": "low",
        "categoria": "manutenibilidade",
        "titulo": "titulo",
        "causa": "causa",
        "remediacao": "remediacao",
    }


class TestVariavelNomeCurto:
    def test_dispara_para_variavel_de_1_char_fora_da_lista(self) -> None:
        entrada = {
            "caminho": "api/x.py",
            "conteudo": "zz = calcular()\n",
            "regra": _regra(),
        }
        saida = avaliar_rev006(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_para_abreviacao_na_lista_de_excecoes(self) -> None:
        entrada = {
            "caminho": "api/x.py",
            "conteudo": "db = conectar()\n",
            "regra": _regra(),
        }
        saida = avaliar_rev006(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_para_arquivo_de_teste(self) -> None:
        entrada = {
            "caminho": "tests/test_algo.py",
            "conteudo": "zz = calcular()\n",
            "regra": _regra(),
        }
        saida = avaliar_rev006(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_para_loop_curto(self) -> None:
        entrada = {
            "caminho": "api/x.py",
            "conteudo": "for zz in range(10):\n    pass\n",
            "regra": _regra(),
        }
        saida = avaliar_rev006(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_para_comparacao(self) -> None:
        entrada = {
            "caminho": "api/x.py",
            "conteudo": "if zz == 1:\n    pass\n",
            "regra": _regra(),
        }
        saida = avaliar_rev006(entrada, _contexto())
        assert saida["achados"] == []

    def test_multiplas_variaveis_curtas_agregam_num_unico_achado(self) -> None:
        entrada = {
            "caminho": "api/x.py",
            "conteudo": "zz = 1\nyy = 2\n",
            "regra": _regra(),
        }
        saida = avaliar_rev006(entrada, _contexto())
        assert len(saida["achados"]) == 1
        assert "1" in saida["achados"][0]["descricao"]
        assert "2" in saida["achados"][0]["descricao"]
