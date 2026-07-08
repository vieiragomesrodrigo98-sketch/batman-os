"""Testes do handler bespoke QA-AUTO-001 "router sem arquivo de teste
correspondente" (`qaauto001_router_sem_teste.py`)."""

from __future__ import annotations

import json

from batman_os.capabilities.operator import ExecutionContext
from batman_os.capabilities.rules.qaauto001_router_sem_teste import avaliar_qaauto001
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
        "codigo": "QA-AUTO-001",
        "agente": "qa-automation",
        "severidade": "medium",
        "categoria": "cobertura",
        "titulo": "titulo",
        "causa": "causa",
        "remediacao": "remediacao",
    }


class TestRouterSemTeste:
    def test_dispara_quando_nao_ha_teste_correspondente(self) -> None:
        entrada = {
            "caminho": "api/routers/pedidos.py",
            "conteudo": json.dumps({"test_stems": ["outra_coisa"]}),
            "regra": _regra(),
        }
        saida = avaliar_qaauto001(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_quando_ha_teste_com_o_mesmo_stem(self) -> None:
        entrada = {
            "caminho": "api/routers/pedidos.py",
            "conteudo": json.dumps({"test_stems": ["pedidos"]}),
            "regra": _regra(),
        }
        saida = avaliar_qaauto001(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_para_init(self) -> None:
        entrada = {
            "caminho": "api/routers/__init__.py",
            "conteudo": json.dumps({"test_stems": []}),
            "regra": _regra(),
        }
        saida = avaliar_qaauto001(entrada, _contexto())
        assert saida["achados"] == []
