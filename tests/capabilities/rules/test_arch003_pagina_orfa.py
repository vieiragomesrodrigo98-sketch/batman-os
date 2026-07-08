"""Testes do handler bespoke ARCH-003 "página Streamlit órfã"
(`arch003_pagina_orfa.py`)."""

from __future__ import annotations

from batman_os.capabilities.operator import ExecutionContext
from batman_os.capabilities.rules.arch003_pagina_orfa import avaliar_arch003
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
        "codigo": "ARCH-003",
        "agente": "software-architect",
        "severidade": "medium",
        "categoria": "navigation",
        "titulo": "titulo",
        "causa": "causa",
        "remediacao": "remediacao",
        "caminho_agregador": "dashboard/app.py",
    }


class TestPaginaOrfa:
    def test_dispara_quando_stem_nao_aparece_no_agregador(self) -> None:
        entrada = {
            "caminho": "pages/orfa.py",
            "conteudo": "import outra_pagina\n",
            "regra": _regra(),
        }
        saida = avaliar_arch003(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_quando_stem_aparece_no_agregador(self) -> None:
        entrada = {
            "caminho": "pages/registrada.py",
            "conteudo": "import registrada\n",
            "regra": _regra(),
        }
        saida = avaliar_arch003(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_quando_agregador_nao_existe(self) -> None:
        entrada = {
            "caminho": "pages/orfa.py",
            "conteudo": None,
            "regra": _regra(),
        }
        saida = avaliar_arch003(entrada, _contexto())
        assert saida["achados"] == []
