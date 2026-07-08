"""Testes do handler bespoke QA-AUTO-003 "spec Playwright P0 ausente"
(`qaauto003_smoke_specs_ausentes.py`)."""

from __future__ import annotations

import json

from batman_os.capabilities.operator import ExecutionContext
from batman_os.capabilities.rules.qaauto003_smoke_specs_ausentes import avaliar_qaauto003
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
        "codigo": "QA-AUTO-003",
        "agente": "qa-automation",
        "severidade": "medium",
        "categoria": "cobertura",
        "titulo": "titulo",
        "causa": "causa",
        "remediacao": "remediacao",
    }


class TestSmokeSpecsAusentes:
    def test_dispara_quando_ha_specs_ausentes(self) -> None:
        entrada = {
            "caminho": "e2e/smoke",
            "conteudo": json.dumps(
                {"missing": ["e2e/smoke/landing.spec.ts", "e2e/smoke/i18n.spec.ts"], "total": 7}
            ),
            "regra": _regra(),
        }
        saida = avaliar_qaauto003(entrada, _contexto())
        assert len(saida["achados"]) == 1
        assert "2/7" in saida["achados"][0]["descricao"]
        assert saida["achados"][0]["arquivo"] == "e2e/smoke/landing.spec.ts"

    def test_nao_dispara_quando_todos_presentes(self) -> None:
        entrada = {
            "caminho": "e2e/smoke",
            "conteudo": json.dumps({"missing": [], "total": 7}),
            "regra": _regra(),
        }
        saida = avaliar_qaauto003(entrada, _contexto())
        assert saida["achados"] == []
