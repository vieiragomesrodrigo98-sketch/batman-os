"""Testes do handler bespoke UI-002 "style inline estático"
(`ui002_inline_style_estatico.py`)."""

from __future__ import annotations

from batman_os.capabilities.operator import ExecutionContext
from batman_os.capabilities.rules.ui002_inline_style_estatico import avaliar_ui002
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
        "codigo": "UI-002",
        "agente": "ui-designer",
        "severidade": "low",
        "categoria": "design-system",
        "titulo": "titulo",
        "causa": "causa",
        "remediacao": "remediacao",
    }


class TestInlineStyleEstatico:
    def test_dispara_para_style_com_valores_literais(self) -> None:
        entrada = {
            "caminho": "frontend/src/Card.tsx",
            "conteudo": "<div style={{ color: 'red', padding: 10 }}>x</div>\n",
            "regra": _regra(),
        }
        saida = avaliar_ui002(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_para_style_com_variavel(self) -> None:
        entrada = {
            "caminho": "frontend/src/Card.tsx",
            "conteudo": "<div style={{ color: theme.colors.primary }}>x</div>\n",
            "regra": _regra(),
        }
        saida = avaliar_ui002(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_para_shorthand(self) -> None:
        entrada = {
            "caminho": "frontend/src/Card.tsx",
            "conteudo": "<div style={{ color }}>x</div>\n",
            "regra": _regra(),
        }
        saida = avaliar_ui002(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_para_template_literal(self) -> None:
        entrada = {
            "caminho": "frontend/src/Card.tsx",
            "conteudo": "<div style={{ color: `${cor}` }}>x</div>\n",
            "regra": _regra(),
        }
        saida = avaliar_ui002(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_sem_style_inline(self) -> None:
        entrada = {
            "caminho": "frontend/src/Card.tsx",
            "conteudo": "<div className='card'>x</div>\n",
            "regra": _regra(),
        }
        saida = avaliar_ui002(entrada, _contexto())
        assert saida["achados"] == []
