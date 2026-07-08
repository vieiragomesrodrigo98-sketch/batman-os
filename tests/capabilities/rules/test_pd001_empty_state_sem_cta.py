"""Testes do handler bespoke PD-001 "empty state sem CTA"
(`pd001_empty_state_sem_cta.py`)."""

from __future__ import annotations

from batman_os.capabilities.operator import ExecutionContext
from batman_os.capabilities.rules.pd001_empty_state_sem_cta import avaliar_pd001
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
        "codigo": "PD-001",
        "agente": "product-designer",
        "severidade": "medium",
        "categoria": "completude",
        "titulo": "titulo",
        "causa": "causa",
        "remediacao": "remediacao",
    }


class TestEmptyStateSemCta:
    def test_dispara_quando_empty_state_sem_cta_na_vizinhanca(self) -> None:
        entrada = {
            "caminho": "frontend/src/Signals.tsx",
            "conteudo": "<div>Nenhum sinal encontrado</div>\n",
            "regra": _regra(),
        }
        saida = avaliar_pd001(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_quando_ha_cta_na_vizinhanca(self) -> None:
        entrada = {
            "caminho": "frontend/src/Signals.tsx",
            "conteudo": (
                '<div>Nenhum sinal encontrado</div>\n<Link to="/explorar">Explorar →</Link>\n'
            ),
            "regra": _regra(),
        }
        saida = avaliar_pd001(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_sem_mensagem_de_empty_state(self) -> None:
        entrada = {
            "caminho": "frontend/src/Signals.tsx",
            "conteudo": "<div>Ola mundo</div>\n",
            "regra": _regra(),
        }
        saida = avaliar_pd001(entrada, _contexto())
        assert saida["achados"] == []

    def test_so_a_primeira_ocorrencia_importa(self) -> None:
        # 2 ocorrencias no mesmo arquivo, mas so a 1a e' checada -> 1 achado
        entrada = {
            "caminho": "frontend/src/Signals.tsx",
            "conteudo": (
                "<div>Nenhum sinal encontrado</div>\n<div>Nenhuma posição encontrada</div>\n"
            ),
            "regra": _regra(),
        }
        saida = avaliar_pd001(entrada, _contexto())
        assert len(saida["achados"]) == 1
