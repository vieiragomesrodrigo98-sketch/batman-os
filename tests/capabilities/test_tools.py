"""Testes de Tools (Vol.IV Cap.18) — AT-18.1 a AT-18.3."""

from __future__ import annotations

from datetime import timedelta
from typing import Literal

import pytest

from batman_os.capabilities.tools import (
    CircuitBreakerPorTool,
    CredencialLiteralDetectada,
    CredentialRef,
    Environment,
    EstadoCircuitBreaker,
    FailureBehavior,
    ToolDefinition,
    ToolRegistry,
    ToolResolutionAmbiguity,
)
from batman_os.foundation.types import SkillId, TenantId, Timestamp, ToolId, agora

TENANT_A = TenantId("tenant-a")
TENANT_B = TenantId("tenant-b")


def _tool(
    id_: str,
    skill: str = "git",
    environment: Environment = Environment.PRODUCTION,
    tenant_scope: list[TenantId] | Literal["all"] = "all",
    cofre: str = "vault-prod",
    caminho: str = "secret/git/token",
) -> ToolDefinition:
    return ToolDefinition(
        id=ToolId(id_),
        implements_skill=SkillId(skill),
        environment=environment,
        tenant_scope=tenant_scope,
        credentials_ref=CredentialRef(cofre=cofre, caminho=caminho),
        failure_behavior=FailureBehavior.FAIL_FAST,
    )


class _RelogioFalso:
    def __init__(self) -> None:
        self._agora = agora()

    def __call__(self) -> Timestamp:
        return self._agora

    def avancar(self, segundos: float) -> None:
        self._agora = self._agora + timedelta(seconds=segundos)


class TestAT181ResolucaoExigeExatamenteUmCandidato:
    def test_zero_candidatos_levanta_ambiguidade(self) -> None:
        registry = ToolRegistry()
        with pytest.raises(ToolResolutionAmbiguity):
            registry.resolve_tool(SkillId("git"), TENANT_A, Environment.PRODUCTION)

    def test_um_candidato_e_resolvido(self) -> None:
        registry = ToolRegistry()
        registry.register(_tool("github-api-v3-prod"))

        resolvida = registry.resolve_tool(SkillId("git"), TENANT_A, Environment.PRODUCTION)
        assert resolvida.id == ToolId("github-api-v3-prod")

    def test_multiplos_candidatos_levanta_ambiguidade(self) -> None:
        registry = ToolRegistry()
        registry.register(_tool("github-api-v3-prod"))
        registry.register(_tool("github-api-v4-prod"))  # mesma skill+tenant+ambiente

        with pytest.raises(ToolResolutionAmbiguity):
            registry.resolve_tool(SkillId("git"), TENANT_A, Environment.PRODUCTION)

    def test_escopo_de_tenant_filtra_candidatos(self) -> None:
        registry = ToolRegistry()
        registry.register(_tool("tool-tenant-a", tenant_scope=[TENANT_A]))
        registry.register(_tool("tool-tenant-b", tenant_scope=[TENANT_B]))

        resolvida = registry.resolve_tool(SkillId("git"), TENANT_A, Environment.PRODUCTION)
        assert resolvida.id == ToolId("tool-tenant-a")

    def test_escopo_de_ambiente_filtra_candidatos(self) -> None:
        registry = ToolRegistry()
        registry.register(_tool("tool-prod", environment=Environment.PRODUCTION))
        registry.register(_tool("tool-staging", environment=Environment.STAGING))

        resolvida = registry.resolve_tool(SkillId("git"), TENANT_A, Environment.STAGING)
        assert resolvida.id == ToolId("tool-staging")


class TestAT182NuncaCredencialLiteral:
    def test_valor_estilo_aws_access_key_e_rejeitado(self) -> None:
        with pytest.raises(CredencialLiteralDetectada):
            ToolRegistry().register(_tool("t", caminho="AKIAABCDEFGHIJKLMNOP"))

    def test_valor_estilo_api_key_sk_e_rejeitado(self) -> None:
        with pytest.raises(CredencialLiteralDetectada):
            ToolRegistry().register(_tool("t", caminho="sk-abcdefghijklmnopqrstuvwxyz123456"))

    def test_valor_estilo_jwt_e_rejeitado(self) -> None:
        jwt_falso = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dQw4w9WgXcQ_abcdefghij"
        with pytest.raises(CredencialLiteralDetectada):
            ToolRegistry().register(_tool("t", caminho=jwt_falso))

    def test_referencia_opaca_normal_e_aceita(self) -> None:
        registry = ToolRegistry()
        registry.register(_tool("t", cofre="vault-prod", caminho="secret/data/git-token"))
        assert registry.resolve_tool(SkillId("git"), TENANT_A, Environment.PRODUCTION)


class TestAT183CircuitBreakerRejeitaEmTempoConstante:
    def test_abre_apos_taxa_de_falha_exceder_limiar(self) -> None:
        cb = CircuitBreakerPorTool(
            limiar_taxa_falha=0.5, tamanho_janela=4, segundos_resfriamento=30
        )

        for sucesso in [True, True, False, False]:
            cb.registrar_resultado(sucesso)

        assert cb.estado == EstadoCircuitBreaker.OPEN
        assert cb.permite_chamada() is False

    def test_meio_aberto_apos_resfriamento_e_fecha_com_sucesso(self) -> None:
        relogio = _RelogioFalso()
        cb = CircuitBreakerPorTool(
            limiar_taxa_falha=0.5, tamanho_janela=2, segundos_resfriamento=10, relogio=relogio
        )
        cb.registrar_resultado(False)
        cb.registrar_resultado(False)
        assert cb.estado == EstadoCircuitBreaker.OPEN

        relogio.avancar(10)
        assert cb.permite_chamada() is True
        assert cb.estado == EstadoCircuitBreaker.HALF_OPEN  # type: ignore[comparison-overlap]

        cb.registrar_resultado(True)
        assert cb.estado == EstadoCircuitBreaker.CLOSED

    def test_meio_aberto_volta_a_abrir_se_teste_falha(self) -> None:
        relogio = _RelogioFalso()
        cb = CircuitBreakerPorTool(
            limiar_taxa_falha=0.5, tamanho_janela=2, segundos_resfriamento=10, relogio=relogio
        )
        cb.registrar_resultado(False)
        cb.registrar_resultado(False)
        relogio.avancar(10)
        cb.permite_chamada()  # transiciona para HalfOpen

        cb.registrar_resultado(False)
        assert cb.estado == EstadoCircuitBreaker.OPEN

    def test_rejeita_sem_esperar_resfriamento_antes_do_prazo(self) -> None:
        relogio = _RelogioFalso()
        cb = CircuitBreakerPorTool(
            limiar_taxa_falha=0.5, tamanho_janela=2, segundos_resfriamento=30, relogio=relogio
        )
        cb.registrar_resultado(False)
        cb.registrar_resultado(False)

        relogio.avancar(5)  # bem antes do resfriamento de 30s
        assert cb.permite_chamada() is False
        assert cb.estado == EstadoCircuitBreaker.OPEN

    def test_fechado_por_padrao_permite_chamadas(self) -> None:
        cb = CircuitBreakerPorTool(
            limiar_taxa_falha=0.5, tamanho_janela=4, segundos_resfriamento=30
        )
        assert cb.estado == EstadoCircuitBreaker.CLOSED
        assert cb.permite_chamada() is True
