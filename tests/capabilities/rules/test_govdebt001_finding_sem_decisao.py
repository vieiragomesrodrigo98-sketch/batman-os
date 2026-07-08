"""Testes do handler bespoke GOVDEBT-001 "finding aberto sem decisão há
2+ sessões" (`govdebt001_finding_sem_decisao.py`)."""

from __future__ import annotations

import json

from batman_os.capabilities.operator import ExecutionContext
from batman_os.capabilities.rules.govdebt001_finding_sem_decisao import avaliar_govdebt001
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
        "codigo": "GOVDEBT-001",
        "agente": "governance-debt",
        "severidade": "high",
        "categoria": "governança",
        "titulo": "titulo",
        "causa": "causa",
        "remediacao": "remediacao",
    }


def _entry(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "status": "open",
        "sessoes_aberto": 3,
        "codigo": "SEC-001",
        "agente": "security-engineer",
        "titulo": "t",
        "descricao": "d",
    }
    base.update(overrides)
    return base


class TestFindingSemDecisao:
    def test_dispara_para_finding_aberto_2_sessoes_sem_deferimento(self) -> None:
        entrada = {
            "caminho": "Batman/ledger.json",
            "conteudo": json.dumps(
                {"ledger": {"entries": {"fp1": _entry()}}, "deferred_codes": []}
            ),
            "regra": _regra(),
        }
        saida = avaliar_govdebt001(entrada, _contexto())
        assert len(saida["achados"]) == 1
        assert saida["achados"][0]["chave"] == "fp1"

    def test_nao_dispara_sem_ledger(self) -> None:
        entrada = {"caminho": "Batman/ledger.json", "conteudo": None, "regra": _regra()}
        saida = avaliar_govdebt001(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_para_finding_fechado(self) -> None:
        entrada = {
            "caminho": "Batman/ledger.json",
            "conteudo": json.dumps(
                {"ledger": {"entries": {"fp1": _entry(status="fixed")}}, "deferred_codes": []}
            ),
            "regra": _regra(),
        }
        saida = avaliar_govdebt001(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_abaixo_do_threshold_de_sessoes(self) -> None:
        entrada = {
            "caminho": "Batman/ledger.json",
            "conteudo": json.dumps(
                {"ledger": {"entries": {"fp1": _entry(sessoes_aberto=1)}}, "deferred_codes": []}
            ),
            "regra": _regra(),
        }
        saida = avaliar_govdebt001(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_para_codigo_deferido(self) -> None:
        entrada = {
            "caminho": "Batman/ledger.json",
            "conteudo": json.dumps(
                {
                    "ledger": {"entries": {"fp1": _entry()}},
                    "deferred_codes": ["SEC-001"],
                }
            ),
            "regra": _regra(),
        }
        saida = avaliar_govdebt001(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_se_auto_referencia(self) -> None:
        entrada = {
            "caminho": "Batman/ledger.json",
            "conteudo": json.dumps(
                {
                    "ledger": {"entries": {"fp1": _entry(codigo="GOVDEBT-001")}},
                    "deferred_codes": [],
                }
            ),
            "regra": _regra(),
        }
        saida = avaliar_govdebt001(entrada, _contexto())
        assert saida["achados"] == []

    def test_multiplos_findings_elegiveis_produzem_multiplos_achados(self) -> None:
        entrada = {
            "caminho": "Batman/ledger.json",
            "conteudo": json.dumps(
                {
                    "ledger": {
                        "entries": {
                            "fp1": _entry(codigo="SEC-001"),
                            "fp2": _entry(codigo="BE-001"),
                        }
                    },
                    "deferred_codes": [],
                }
            ),
            "regra": _regra(),
        }
        saida = avaliar_govdebt001(entrada, _contexto())
        assert len(saida["achados"]) == 2
        chaves = {a["chave"] for a in saida["achados"]}
        assert chaves == {"fp1", "fp2"}
