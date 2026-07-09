"""Testes do handler bespoke A11Y-002 "onClick em elemento não-interativo
sem suporte a teclado" (`a11y002_onclick_sem_teclado.py`)."""

from __future__ import annotations

from batman_os.capabilities.operator import ExecutionContext
from batman_os.capabilities.rules.a11y002_onclick_sem_teclado import avaliar_a11y002
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
        "codigo": "A11Y-002",
        "agente": "ux-designer",
        "severidade": "low",
        "categoria": "acessibilidade",
        "titulo": "titulo",
        "causa": "causa",
        "remediacao": "remediacao",
    }


class TestOnClickSemTeclado:
    def test_dispara_para_div_com_onclick_sem_teclado(self) -> None:
        entrada = {
            "caminho": "frontend/src/Card.tsx",
            "conteudo": "<div onClick={handleClick}>texto</div>\n",
            "regra": _regra(),
        }
        saida = avaliar_a11y002(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_com_role_e_onkeydown(self) -> None:
        entrada = {
            "caminho": "frontend/src/Card.tsx",
            "conteudo": (
                '<div onClick={handleClick} role="button" onKeyDown={handleKey}>texto</div>\n'
            ),
            "regra": _regra(),
        }
        saida = avaliar_a11y002(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_sem_onclick(self) -> None:
        entrada = {
            "caminho": "frontend/src/Card.tsx",
            "conteudo": "<div>texto</div>\n",
            "regra": _regra(),
        }
        saida = avaliar_a11y002(entrada, _contexto())
        assert saida["achados"] == []

    def test_lida_com_chaves_dentro_da_tag(self) -> None:
        entrada = {
            "caminho": "frontend/src/Card.tsx",
            "conteudo": "<div className={x > 0 ? 'a' : 'b'} onClick={handleClick}>texto</div>\n",
            "regra": _regra(),
        }
        saida = avaliar_a11y002(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_sem_conteudo(self) -> None:
        entrada = {"caminho": "frontend/src/x.tsx", "conteudo": None, "regra": _regra()}
        saida = avaliar_a11y002(entrada, _contexto())
        assert saida["achados"] == []
