"""Testes do handler bespoke SWEEP-001 "rodízio de sweeps fora da
cadência" (`sweep001_cadencia_quebrada.py`)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from batman_os.capabilities.operator import ExecutionContext
from batman_os.capabilities.rules.sweep001_cadencia_quebrada import avaliar_sweep001
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
        "codigo": "SWEEP-001",
        "agente": "skill-sweep",
        "severidade": "medium",
        "categoria": "governança",
        "titulo": "titulo",
        "causa": "causa",
        "remediacao": "remediacao",
    }


class TestCadenciaQuebrada:
    def test_dispara_quando_rotacao_nao_inicializada(self) -> None:
        entrada = {
            "caminho": "Batman/config/sweep_state.json",
            "conteudo": None,
            "regra": _regra(),
        }
        saida = avaliar_sweep001(entrada, _contexto())
        assert len(saida["achados"]) == 1
        assert saida["achados"][0]["chave"] == "nao-inicializado"

    def test_dispara_quando_rotacao_parada(self) -> None:
        entrada = {
            "caminho": "Batman/config/sweep_state.json",
            "conteudo": json.dumps({"cadencia_dias": 7, "atual": None}),
            "regra": _regra(),
        }
        saida = avaliar_sweep001(entrada, _contexto())
        assert len(saida["achados"]) == 1
        assert saida["achados"][0]["chave"] == "parado"

    def test_dispara_quando_atribuido_ha_mais_dias_que_a_cadencia(self) -> None:
        antigo = (datetime.now(UTC) - timedelta(days=10)).isoformat()
        entrada = {
            "caminho": "Batman/config/sweep_state.json",
            "conteudo": json.dumps(
                {
                    "cadencia_dias": 7,
                    "atual": {
                        "papel": "security-engineer",
                        "atribuido_em": antigo,
                        "status": "pendente",
                    },
                }
            ),
            "regra": _regra(),
        }
        saida = avaliar_sweep001(entrada, _contexto())
        assert len(saida["achados"]) == 1
        assert saida["achados"][0]["chave"] == "security-engineer"

    def test_nao_dispara_dentro_da_cadencia(self) -> None:
        recente = datetime.now(UTC).isoformat()
        entrada = {
            "caminho": "Batman/config/sweep_state.json",
            "conteudo": json.dumps(
                {
                    "cadencia_dias": 7,
                    "atual": {
                        "papel": "security-engineer",
                        "atribuido_em": recente,
                        "status": "pendente",
                    },
                }
            ),
            "regra": _regra(),
        }
        saida = avaliar_sweep001(entrada, _contexto())
        assert saida["achados"] == []
