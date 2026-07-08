"""Testes do handler bespoke DOC-004 "CHANGELOG.md sem versão
correspondente" (`doc004_changelog_sem_versao.py`)."""

from __future__ import annotations

import json

from batman_os.capabilities.operator import ExecutionContext
from batman_os.capabilities.rules.doc004_changelog_sem_versao import avaliar_doc004
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
        "codigo": "DOC-004",
        "agente": "technical-writer",
        "severidade": "low",
        "categoria": "documentacao",
        "titulo": "titulo",
        "causa": "causa",
        "remediacao": "remediacao",
    }


class TestChangelogSemVersao:
    def test_dispara_quando_versao_nao_esta_no_changelog(self) -> None:
        entrada = {
            "caminho": "CHANGELOG.md",
            "conteudo": json.dumps(
                {
                    "pyproject_texto": '[project]\nversion = "1.2.3"\n',
                    "changelog_texto": "## 1.0.0\n- inicial\n",
                }
            ),
            "regra": _regra(),
        }
        saida = avaliar_doc004(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_quando_versao_esta_no_changelog(self) -> None:
        entrada = {
            "caminho": "CHANGELOG.md",
            "conteudo": json.dumps(
                {
                    "pyproject_texto": '[project]\nversion = "1.2.3"\n',
                    "changelog_texto": "## 1.2.3\n- release atual\n",
                }
            ),
            "regra": _regra(),
        }
        saida = avaliar_doc004(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_sem_pyproject_ou_changelog(self) -> None:
        entrada = {"caminho": "CHANGELOG.md", "conteudo": None, "regra": _regra()}
        saida = avaliar_doc004(entrada, _contexto())
        assert saida["achados"] == []
