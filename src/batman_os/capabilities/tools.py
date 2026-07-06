"""Vol. IV, Cap. 18 — Ferramentas (Tools).

Camada de adaptação concreta que conecta uma Skill ao mundo externo real —
uma API específica, um binário de linha de comando, um SDK. Distinção
formal: Skill é "como fazer" (técnica), Tool é "com o quê, exatamente"
(binding concreto, sujeito a credenciais e escopo de ambiente/tenant).

Fonte da verdade: docs/spec/04-capabilities/04-tools.md
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Mapping
from enum import StrEnum
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from batman_os.foundation.types import SkillId, TenantId, Timestamp, ToolId, agora


class Environment(StrEnum):
    """Vol.IV Cap.18, secao 18.3."""

    PRODUCTION = "production"
    STAGING = "staging"
    SANDBOX = "sandbox"


class FailureBehavior(StrEnum):
    """Vol.IV Cap.18, secao 18.3."""

    FAIL_FAST = "fail-fast"
    CIRCUIT_BREAK = "circuit-break"


class CredentialRef(BaseModel):
    """Vol.IV Cap.18, secao 18.3 — referência opaca a um cofre de segredos
    externo (Vault, AWS Secrets Manager). NUNCA a credencial em si (AT-18.2,
    regra inegociável)."""

    cofre: str
    caminho: str


class SecretNaoEncontrado(Exception):
    """Vol.VIII Cap.33 (Milestone 7 desta construção) — `SecretResolver`
    não encontrou o segredo referenciado. Nunca degrada para string vazia/
    `None` em silêncio: uma `CredentialRef` sem segredo resolvível é sempre
    um erro de configuração explícito."""


class SecretResolver(Protocol):
    """Vol.VIII Cap.33 (Milestone 7 desta construção) — resolve uma
    `CredentialRef` opaca para o valor real do segredo. Mantém a garantia
    de AT-18.2 (nunca a credencial literal em código/config): o valor real
    só existe fora deste módulo, atrás desta interface."""

    def resolver(self, ref: CredentialRef) -> str: ...


class EnvVarSecretResolver:
    """Vol.VIII Cap.33 — implementação padrão (v1): lê de variável de
    ambiente. NÃO é um cofre externo real (Vault/AWS Secrets Manager) —
    documentado deliberadamente como o mínimo que já elimina segredo em
    texto plano no código/config; um `SecretResolver` que fale com um
    cofre real é extensão natural, sem mudar o Protocol.

    Convenção de nome de variável: `f"{cofre}_{caminho}"`, maiúsculo, com
    `-`/`/` normalizados para `_` (ex.: `CredentialRef(cofre="anthropic",
    caminho="api-key")` -> `ANTHROPIC_API_KEY`)."""

    def __init__(self, env: Mapping[str, str] | None = None) -> None:
        self._env = env if env is not None else os.environ

    def resolver(self, ref: CredentialRef) -> str:
        nome_var = f"{ref.cofre}_{ref.caminho}".upper().replace("-", "_").replace("/", "_")
        valor = self._env.get(nome_var)
        if valor is None:
            raise SecretNaoEncontrado(
                f"CredentialRef(cofre='{ref.cofre}', caminho='{ref.caminho}') nao "
                f"resolvido — variavel de ambiente '{nome_var}' ausente"
            )
        return valor


class RateLimitPolicy(BaseModel):
    """Vol.IV Cap.18, secao 18.3."""

    requisicoes_por_segundo: float | None = None
    rajada_maxima: int | None = None


class ToolDefinition(BaseModel):
    """Vol.IV Cap.18, secao 18.3."""

    id: ToolId
    implements_skill: SkillId
    environment: Environment
    tenant_scope: list[TenantId] | Literal["all"]
    credentials_ref: CredentialRef
    rate_limits: RateLimitPolicy = Field(default_factory=RateLimitPolicy)
    failure_behavior: FailureBehavior


def resolver_credential(tool: ToolDefinition, resolver: SecretResolver) -> str:
    """Vol.VIII Cap.33 — ponto único pelo qual uma `ToolDefinition` já
    resolvida (`ToolRegistry.resolve_tool`) obtém o valor real do segredo,
    através do `SecretResolver` injetado — nunca inline, nunca direto de
    `os.environ` espalhado pelo código de cada Tool."""
    return resolver.resolver(tool.credentials_ref)


class CredencialLiteralDetectada(Exception):
    """Vol.IV Cap.18, secao 18.3 (AT-18.2) — `credentialsRef` continha um
    valor que parece uma credencial literal (chave de API, token, JWT), não
    uma referência opaca a cofre externo. Rejeitado no registro."""


class ToolResolutionAmbiguity(Exception):
    """Vol.IV Cap.18, secao 18.4 (AT-18.1) — zero ou múltiplos candidatos
    para a mesma Skill+tenant+ambiente é sempre erro de configuração
    explícito, nunca resolvido por heurística de runtime."""

    def __init__(self, motivo: str, evidencia: dict[str, object] | None = None) -> None:
        super().__init__(motivo)
        self.evidencia = evidencia or {}


# Padroes heuristicos de credencial literal (AT-18.2) — scanner estatico
# simples no processo de registro. Nao substitui um scanner de segredos
# completo (fora de escopo desta construcao); cobre os formatos mais comuns
# o suficiente para nunca aceitar "de graca" um valor obviamente sensivel.
_PADROES_CREDENCIAL_LITERAL = (
    re.compile(r"^AKIA[0-9A-Z]{16}$"),  # AWS access key id
    re.compile(r"^sk-[A-Za-z0-9]{20,}$"),  # estilo API key ("sk-...")
    re.compile(r"^gh[ps]_[A-Za-z0-9]{30,}$"),  # GitHub token
    re.compile(r"^[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}$"),  # JWT
)


def _parece_credencial_literal(valor: str) -> bool:
    return any(padrao.match(valor) for padrao in _PADROES_CREDENCIAL_LITERAL)


class ToolRegistry:
    """Vol.IV Cap.18, secao 18.4."""

    def __init__(self) -> None:
        self._tools: dict[ToolId, ToolDefinition] = {}

    def register(self, definicao: ToolDefinition) -> None:
        """AT-18.2 — rejeita registro se `credentialsRef` parecer conter uma
        credencial literal em vez de uma referência de cofre."""
        if _parece_credencial_literal(
            definicao.credentials_ref.cofre
        ) or _parece_credencial_literal(definicao.credentials_ref.caminho):
            raise CredencialLiteralDetectada(
                f"Tool '{definicao.id}': credentials_ref parece conter uma credencial "
                "literal — deve ser apenas uma referencia opaca a um cofre externo"
            )
        self._tools[definicao.id] = definicao

    def resolve_tool(
        self, skill_id: SkillId, tenant_id: TenantId, ambiente: Environment
    ) -> ToolDefinition:
        """Vol.IV Cap.18, secao 18.4 (AT-18.1) — exige exatamente 1
        candidato; zero ou múltiplos é sempre `ToolResolutionAmbiguity`."""
        candidatos = [t for t in self._tools.values() if t.implements_skill == skill_id]
        candidatos = [
            t for t in candidatos if t.tenant_scope == "all" or tenant_id in t.tenant_scope
        ]
        candidatos = [t for t in candidatos if t.environment == ambiente]

        if len(candidatos) != 1:
            raise ToolResolutionAmbiguity(
                f"Esperado exatamente 1 candidato para skill='{skill_id}' "
                f"tenant='{tenant_id}' ambiente='{ambiente.value}', "
                f"encontrado {len(candidatos)}",
                evidencia={
                    "skill_id": skill_id,
                    "tenant_id": tenant_id,
                    "ambiente": ambiente.value,
                    "candidatos": [t.id for t in candidatos],
                },
            )
        return candidatos[0]


class EstadoCircuitBreaker(StrEnum):
    """Vol.IV Cap.18, secao 18.5."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half-open"


class CircuitBreakerPorTool:
    """Vol.IV Cap.18, secao 18.5 (AT-18.3) — independente do circuit breaker
    de escalonamento a LLM (Vol.II Cap.8, secao 8.6). Janela deslizante de
    resultados; abre quando a taxa de falha excede o limiar configurado."""

    def __init__(
        self,
        limiar_taxa_falha: float,
        tamanho_janela: int,
        segundos_resfriamento: float,
        relogio: Callable[[], Timestamp] = agora,
    ) -> None:
        self._limiar = limiar_taxa_falha
        self._tamanho_janela = tamanho_janela
        self._segundos_resfriamento = segundos_resfriamento
        self._relogio = relogio
        self._estado = EstadoCircuitBreaker.CLOSED
        self._resultados: list[bool] = []
        self._aberto_desde: Timestamp | None = None

    @property
    def estado(self) -> EstadoCircuitBreaker:
        return self._estado

    def permite_chamada(self) -> bool:
        """AT-18.3 — em `Open`, rejeita em tempo constante, sem tentar a
        chamada externa (o próprio ponto do circuit breaker: poupar recurso
        e evitar degradação em cascata)."""
        if self._estado == EstadoCircuitBreaker.OPEN:
            if self._aberto_desde is not None:
                decorrido = (self._relogio() - self._aberto_desde).total_seconds()
                if decorrido >= self._segundos_resfriamento:
                    self._estado = EstadoCircuitBreaker.HALF_OPEN
                    return True
            return False
        return True

    def registrar_resultado(self, sucesso: bool) -> None:
        """Vol.IV Cap.18, secao 18.5 — diagrama de transição."""
        if self._estado == EstadoCircuitBreaker.HALF_OPEN:
            if sucesso:
                self._estado = EstadoCircuitBreaker.CLOSED
                self._resultados = []
            else:
                self._estado = EstadoCircuitBreaker.OPEN
                self._aberto_desde = self._relogio()
            return

        self._resultados.append(sucesso)
        if len(self._resultados) > self._tamanho_janela:
            self._resultados.pop(0)

        if len(self._resultados) >= self._tamanho_janela:
            taxa_falha = self._resultados.count(False) / len(self._resultados)
            if taxa_falha >= self._limiar:
                self._estado = EstadoCircuitBreaker.OPEN
                self._aberto_desde = self._relogio()
