"""Testes do handler bespoke FE-001 "export duplicado entre arquivos"
(`fe001_export_duplicado.py`)."""

from __future__ import annotations

import json

from batman_os.capabilities.operator import ExecutionContext
from batman_os.capabilities.rules.fe001_export_duplicado import avaliar_fe001
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
        "codigo": "FE-001",
        "agente": "frontend-engineer",
        "severidade": "high",
        "categoria": "api",
        "titulo": "titulo",
        "causa": "causa",
        "remediacao": "remediacao",
    }


class TestExportDuplicado:
    def test_dispara_quando_mesmo_nome_exportado_em_2_arquivos(self) -> None:
        entrada = {
            "caminho": "frontend/src/api",
            "conteudo": json.dumps(
                {
                    "arquivos": {
                        "frontend/src/api/a.ts": "export const adminApi = {}\n",
                        "frontend/src/api/b.ts": "export const adminApi = {}\n",
                    }
                }
            ),
            "regra": _regra(),
        }
        saida = avaliar_fe001(entrada, _contexto())
        assert len(saida["achados"]) == 1
        assert saida["achados"][0]["chave"] == "adminApi"
        assert saida["achados"][0]["arquivo"] == "frontend/src/api/a.ts"

    def test_nao_dispara_quando_exports_sao_unicos(self) -> None:
        entrada = {
            "caminho": "frontend/src/api",
            "conteudo": json.dumps(
                {
                    "arquivos": {
                        "frontend/src/api/a.ts": "export const userApi = {}\n",
                        "frontend/src/api/b.ts": "export const adminApi = {}\n",
                    }
                }
            ),
            "regra": _regra(),
        }
        saida = avaliar_fe001(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_quando_mesmo_arquivo_repete_o_export(self) -> None:
        # legado usa set(files) - repeticao do MESMO arquivo nao conta
        # como duplicata entre arquivos distintos.
        entrada = {
            "caminho": "frontend/src/api",
            "conteudo": json.dumps(
                {
                    "arquivos": {
                        "frontend/src/api/a.ts": (
                            "export const userApi = {}\nexport const userApi2 = {}\n"
                        ),
                    }
                }
            ),
            "regra": _regra(),
        }
        saida = avaliar_fe001(entrada, _contexto())
        assert saida["achados"] == []

    def test_multiplos_nomes_duplicados_produzem_multiplos_achados(self) -> None:
        entrada = {
            "caminho": "frontend/src/api",
            "conteudo": json.dumps(
                {
                    "arquivos": {
                        "frontend/src/api/a.ts": (
                            "export const adminApi = {}\nexport const userApi = {}\n"
                        ),
                        "frontend/src/api/b.ts": (
                            "export const adminApi = {}\nexport const userApi = {}\n"
                        ),
                    }
                }
            ),
            "regra": _regra(),
        }
        saida = avaliar_fe001(entrada, _contexto())
        assert len(saida["achados"]) == 2
        chaves = {a["chave"] for a in saida["achados"]}
        assert chaves == {"adminApi", "userApi"}
        fingerprints = {a["fingerprint"] for a in saida["achados"]}
        assert len(fingerprints) == 2
