"""Testes da Skill "comando git único interpretado" (Vol.IV Cap.17)."""

from __future__ import annotations

import pytest

from batman_os.capabilities.capability_contract import certificar
from batman_os.capabilities.operator import ExecutionContext
from batman_os.capabilities.rules.git_comando_interpretado import (
    EntradaInvalida,
    avaliar_regra_git_interpretado,
    construir_implementacao,
)
from batman_os.foundation.types import MissionId, StepId, TenantId, agora
from batman_os.runtime.capability_engine import StatusCapability


def _contexto() -> ExecutionContext:
    return ExecutionContext(
        mission_id=MissionId("m-1"),
        tenant_id=TenantId("t-1"),
        step_id=StepId("s-1"),
        deadline=agora(),
    )


def _regra(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "codigo": "TEST-001",
        "agente": "teste",
        "severidade": "medium",
        "categoria": "cat",
        "titulo": "titulo",
        "causa": "causa",
        "remediacao": "remediacao",
        "limiar": 0,
    }
    base.update(overrides)
    return base


class TestDisparo:
    def test_dispara_quando_numero_acima_do_limiar(self) -> None:
        entrada = {"caminho": ".git", "conteudo": "3", "regra": _regra(limiar=0)}
        saida = avaliar_regra_git_interpretado(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_quando_numero_igual_ao_limiar(self) -> None:
        entrada = {"caminho": ".git", "conteudo": "0", "regra": _regra(limiar=0)}
        saida = avaliar_regra_git_interpretado(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_quando_numero_abaixo_do_limiar(self) -> None:
        entrada = {"caminho": ".git", "conteudo": "2", "regra": _regra(limiar=5)}
        saida = avaliar_regra_git_interpretado(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_com_conteudo_vazio(self) -> None:
        entrada = {"caminho": ".git", "conteudo": "", "regra": _regra()}
        saida = avaliar_regra_git_interpretado(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_com_conteudo_nao_numerico(self) -> None:
        entrada = {"caminho": ".git", "conteudo": "erro: sem upstream", "regra": _regra()}
        saida = avaliar_regra_git_interpretado(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_com_conteudo_none(self) -> None:
        entrada = {"caminho": ".git", "conteudo": None, "regra": _regra()}
        saida = avaliar_regra_git_interpretado(entrada, _contexto())
        assert saida["achados"] == []


class TestEntradaInvalida:
    def test_levanta_excecao_sem_campo_regra(self) -> None:
        with pytest.raises(EntradaInvalida):
            avaliar_regra_git_interpretado({"caminho": ".git"}, _contexto())


class TestCertificacao:
    def test_implementacao_real_passa_na_certificacao(self) -> None:
        impl = construir_implementacao()
        contexto = _contexto()
        entrada_idempotencia = {"caminho": ".git", "conteudo": "3", "regra": _regra()}
        definicao_certificada = certificar(
            impl,
            entrada_para_teste_idempotencia=entrada_idempotencia,
            contexto_para_teste_idempotencia=contexto,
        )
        assert definicao_certificada.status == StatusCapability.ACTIVE
