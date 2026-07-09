"""Testes do handler bespoke FE-002 ".toFixed() sem optional chaining"
(`fe002_tofixed_sem_null_safety.py`)."""

from __future__ import annotations

from batman_os.capabilities.operator import ExecutionContext
from batman_os.capabilities.rules.fe002_tofixed_sem_null_safety import avaliar_fe002
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
        "codigo": "FE-002",
        "agente": "frontend-engineer",
        "severidade": "medium",
        "categoria": "robustez",
        "titulo": "titulo",
        "causa": "causa",
        "remediacao": "remediacao",
    }


class TestToFixedSemNullSafety:
    def test_dispara_para_tofixed_sem_protecao(self) -> None:
        entrada = {
            "caminho": "frontend/src/Card.tsx",
            "conteudo": "const x = valor.toFixed(2);\n",
            "regra": _regra(),
        }
        saida = avaliar_fe002(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_com_optional_chaining(self) -> None:
        entrada = {
            "caminho": "frontend/src/Card.tsx",
            "conteudo": "const x = valor?.toFixed(2);\n",
            "regra": _regra(),
        }
        saida = avaliar_fe002(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_com_null_coalescing(self) -> None:
        entrada = {
            "caminho": "frontend/src/Card.tsx",
            "conteudo": "const x = (valor ?? 0).toFixed(2);\n",
            "regra": _regra(),
        }
        saida = avaliar_fe002(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_com_guard_na_mesma_linha(self) -> None:
        entrada = {
            "caminho": "frontend/src/Card.tsx",
            "conteudo": "const x = valor !== null ? valor.toFixed(2) : '';\n",
            "regra": _regra(),
        }
        saida = avaliar_fe002(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_com_guard_do_mesmo_receptor_em_linha_anterior(self) -> None:
        entrada = {
            "caminho": "frontend/src/Card.tsx",
            "conteudo": "{valor !== null && (\n  <span>{valor.toFixed(2)}</span>\n)}\n",
            "regra": _regra(),
        }
        saida = avaliar_fe002(entrada, _contexto())
        assert saida["achados"] == []

    def test_dispara_com_guard_de_outro_receptor_em_linha_anterior(self) -> None:
        entrada = {
            "caminho": "frontend/src/Card.tsx",
            "conteudo": "{outro !== null && (\n  <span>{valor.toFixed(2)}</span>\n)}\n",
            "regra": _regra(),
        }
        saida = avaliar_fe002(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_para_arquivo_ts_sem_extensao_tsx(self) -> None:
        entrada = {
            "caminho": "frontend/src/utils.ts",
            "conteudo": "const x = valor.toFixed(2);\n",
            "regra": _regra(),
        }
        saida = avaliar_fe002(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_para_componente_admin(self) -> None:
        entrada = {
            "caminho": "frontend/src/MotorAdmin.tsx",
            "conteudo": "const x = valor.toFixed(2);\n",
            "regra": _regra(),
        }
        saida = avaliar_fe002(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_para_arquivo_de_teste(self) -> None:
        entrada = {
            "caminho": "frontend/src/Card.test.tsx",
            "conteudo": "const x = valor.toFixed(2);\n",
            "regra": _regra(),
        }
        saida = avaliar_fe002(entrada, _contexto())
        assert saida["achados"] == []
