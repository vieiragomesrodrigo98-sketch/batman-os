"""Testes do handler da Skill "métrica com limiar"
(`metrica_com_limiar.py`) — foco no modo `contagem_funcoes_nome` e no
operador `<` (achado de extensão para QA-AUTO-002: "dispara quando a
métrica fica ABAIXO do limiar", diferente dos demais modos que disparam
por EXCESSO)."""

from __future__ import annotations

from batman_os.capabilities.operator import ExecutionContext
from batman_os.capabilities.rules.metrica_com_limiar import avaliar_regra_metrica
from batman_os.foundation.types import MissionId, StepId, TenantId, agora


def _contexto() -> ExecutionContext:
    return ExecutionContext(
        mission_id=MissionId("m-1"),
        tenant_id=TenantId("t-1"),
        step_id=StepId("s-1"),
        deadline=agora(),
    )


def _regra_contagem_funcoes(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "codigo": "TEST-001",
        "agente": "teste",
        "severidade": "low",
        "categoria": "cobertura",
        "titulo": "titulo",
        "causa": "causa",
        "remediacao": "remediacao",
        "metrica": "contagem_funcoes_nome",
        "pattern_nome_funcao": "^test_",
        "limiar": 1,
        "operador": "<",
    }
    base.update(overrides)
    return base


class TestContagemFuncoesNome:
    def test_dispara_quando_nenhuma_funcao_test_existe(self) -> None:
        entrada = {
            "caminho": "tests/test_vazio.py",
            "conteudo": "def helper():\n    return 1\n",
            "regra": _regra_contagem_funcoes(),
        }
        saida = avaliar_regra_metrica(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_quando_existe_uma_funcao_test(self) -> None:
        entrada = {
            "caminho": "tests/test_algo.py",
            "conteudo": "def test_algo():\n    assert True\n",
            "regra": _regra_contagem_funcoes(),
        }
        saida = avaliar_regra_metrica(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_com_erro_de_sintaxe(self) -> None:
        entrada = {
            "caminho": "tests/test_quebrado.py",
            "conteudo": "def (:\n",
            "regra": _regra_contagem_funcoes(),
        }
        saida = avaliar_regra_metrica(entrada, _contexto())
        assert saida["achados"] == []
