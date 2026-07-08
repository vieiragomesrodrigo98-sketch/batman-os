"""Testes do handler bespoke PD-011 "diversificação do motor não
comunicada" (`pd011_diversificacao_nao_comunicada.py`)."""

from __future__ import annotations

import json

from batman_os.capabilities.operator import ExecutionContext
from batman_os.capabilities.rules.pd011_diversificacao_nao_comunicada import avaliar_pd011
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
        "codigo": "PD-011",
        "agente": "product-designer",
        "severidade": "low",
        "categoria": "regra-de-negocio",
        "titulo": "titulo",
        "causa": "causa",
        "remediacao": "remediacao",
        "pattern": "MOTOR_CAP01|diversif",
        "ignore_case": True,
    }


class TestDiversificacaoNaoComunicada:
    def test_dispara_quando_regra_ativa_no_backend_sem_comunicacao_no_frontend(self) -> None:
        entrada = {
            "caminho": "frontend/src/",
            "conteudo": json.dumps(
                {"frontend_text": "nada relacionado", "backend_text": "def diversify(): pass"}
            ),
            "regra": _regra(),
        }
        saida = avaliar_pd011(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_quando_frontend_comunica_a_regra(self) -> None:
        entrada = {
            "caminho": "frontend/src/",
            "conteudo": json.dumps(
                {"frontend_text": "tooltip diversificacao", "backend_text": "def diversify()"}
            ),
            "regra": _regra(),
        }
        saida = avaliar_pd011(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_quando_regra_nao_existe_no_backend(self) -> None:
        entrada = {
            "caminho": "frontend/src/",
            "conteudo": json.dumps({"frontend_text": "nada", "backend_text": "nada tambem"}),
            "regra": _regra(),
        }
        saida = avaliar_pd011(entrada, _contexto())
        assert saida["achados"] == []
