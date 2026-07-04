"""Vol. IV, Cap. 15 — O que é um Operador.

O executor especializado do Batman: a entidade concreta que possui
Capacidades, Ferramentas, Memória Operacional, Estado e Permissões, invocada
pelo Execution Engine (Vol.III Cap.12) para realizar o trabalho de um
`PlanStep`.

Fonte da verdade: docs/spec/04-capabilities/01-operator.md
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, Field

from batman_os.foundation.types import (
    CapabilityId,
    MissionId,
    OperatorId,
    StepId,
    TenantId,
    Timestamp,
)


class SideEffectScope(StrEnum):
    """Vol.IV Cap.15, secao 15.5."""

    READ_ONLY = "read-only"
    REVERSIBLE_WRITE = "reversible-write"
    IRREVERSIBLE_WRITE = "irreversible-write"


class PermissionSet(BaseModel):
    """Vol.IV Cap.15, secao 15.5 — princípio de menor privilégio: todo
    Operador nasce com `allowed_actions` vazio; cada ação precisa ser
    explicitamente concedida (whitelist, nunca blacklist)."""

    allowed_actions: list[str] = Field(default_factory=list)
    side_effect_scope: SideEffectScope
    requires_approval_above: float | None = None


class NetworkPolicy(StrEnum):
    """Vol.IV Cap.15, secao 15.6."""

    NONE = "none"
    ALLOWLIST = "allowlist"
    UNRESTRICTED = "unrestricted"


class FilesystemAccess(StrEnum):
    """Vol.IV Cap.15, secao 15.6."""

    NONE = "none"
    SCOPED_TEMP = "scoped-temp"
    SCOPED_PERSISTENT = "scoped-persistent"


class ResourceLimits(BaseModel):
    """Vol.IV Cap.15, secao 15.6 — declaração de limites; o enforcement em
    tempo real já existe no bulkhead do Execution Engine (Vol.III Cap.12,
    `LimitadorDeRecursoPorOperador`)."""

    cpu_ms_max: float | None = None
    memoria_mb_max: float | None = None
    timeout_segundos: float | None = None


class SandboxPolicy(BaseModel):
    """Vol.IV Cap.15, secao 15.6 — campo obrigatório em todo Operador
    registrado, nunca implícito (secao 15.8)."""

    resource_limits: ResourceLimits
    network_policy: NetworkPolicy
    filesystem_access: FilesystemAccess


class ExecutionContext(BaseModel):
    """Vol.IV Cap.15, secao 15.3 — o Operador nunca recebe a `Mission`
    completa, apenas este contexto mínimo (reduz raio de dano de um Operador
    malicioso/defeituoso, reforça isolamento por tenant, ADR-0005)."""

    mission_id: MissionId
    tenant_id: TenantId
    step_id: StepId
    deadline: Timestamp


class HealthStatus(BaseModel):
    """Vol.IV Cap.15, secao 15.3 — consumido pelo Resource Limiter (Vol.III
    Cap.12) para decidir quarentena."""

    saudavel: bool
    detalhes: str = ""


class StatusOperador(StrEnum):
    """Vol.IV Cap.15, secao 15.7."""

    REGISTERED = "registered"
    CERTIFIED = "certified"
    ACTIVE = "active"
    QUARANTINED = "quarantined"
    RETIRED = "retired"


class ExecutorDeOperador(Protocol):
    """A lógica real de execução que um Operador concreto implementa —
    injetada, para não acoplar este módulo a nenhuma tecnologia específica
    (Kubernetes, shell, API externa, etc.)."""

    def executar(
        self, capability_id: CapabilityId, entrada: Any, contexto: ExecutionContext
    ) -> Any: ...

    def health_check(self) -> HealthStatus: ...


class PermissaoNegada(Exception):
    """AT-15.1 — Operador tentou executar ação fora de `allowed_actions`, ou
    enquanto em `Quarantined` (AT-15.2)."""


class RegistroOperadorInvalido(Exception):
    """Vol.IV Cap.15, secao 15.8 — `sideEffectScope: irreversible-write` sem
    `requiresApprovalAbove` (AT-15.3) é rejeitado no registro, sem exceção."""


class TransicaoDeCicloInvalida(Exception):
    """Vol.IV Cap.15, secao 15.7 — transição fora do diagrama de estados."""


_TRANSICOES_VALIDAS: dict[StatusOperador, set[StatusOperador]] = {
    StatusOperador.REGISTERED: {StatusOperador.CERTIFIED},
    StatusOperador.CERTIFIED: {StatusOperador.ACTIVE},
    StatusOperador.ACTIVE: {StatusOperador.QUARANTINED, StatusOperador.RETIRED},
    StatusOperador.QUARANTINED: {StatusOperador.ACTIVE, StatusOperador.RETIRED},
    StatusOperador.RETIRED: set(),
}


class Operator:
    """Vol.IV Cap.15, secao 15.3 — contrato formal + enforcement de
    permissões, sandbox e ciclo de vida.

    Nota de interpretação: `allowed_actions` (secao 15.5) é tratado aqui como
    a whitelist de `CapabilityId`s que este Operador pode executar — a
    especificação declara o campo como `string[]` genérico sem amarrar
    explicitamente à Capability, mas "cada ação precisa ser explicitamente
    concedida" (secao 15.5) casa diretamente com "quais Capabilities este
    Operador pode de fato invocar".
    """

    def __init__(
        self,
        operator_id: OperatorId,
        capabilities: list[CapabilityId],
        permissions: PermissionSet,
        sandbox: SandboxPolicy,
        executor: ExecutorDeOperador,
    ) -> None:
        if (
            permissions.side_effect_scope == SideEffectScope.IRREVERSIBLE_WRITE
            and permissions.requires_approval_above is None
        ):
            raise RegistroOperadorInvalido(
                f"Operador '{operator_id}' com sideEffectScope=irreversible-write "
                "exige requires_approval_above definido (AT-15.3)"
            )

        self.id = operator_id
        self.capabilities = list(capabilities)
        self.permissions = permissions
        self.sandbox = sandbox
        self.status = StatusOperador.REGISTERED
        self._executor = executor

    def execute(self, capability_id: CapabilityId, entrada: Any, contexto: ExecutionContext) -> Any:
        """Vol.IV Cap.15, secao 15.3. AT-15.1: rejeita ação fora de
        `allowed_actions` ANTES de invocar fisicamente o executor — nunca
        toca o mundo real para uma ação não autorizada. AT-15.2: um Operador
        em `Quarantined` rejeita toda nova execução até retornar a `Active`.
        """
        if self.status == StatusOperador.QUARANTINED:
            raise PermissaoNegada(f"Operador '{self.id}' está em quarentena (Quarantined)")
        if capability_id not in self.permissions.allowed_actions:
            raise PermissaoNegada(
                f"Operador '{self.id}' não tem permissão para executar '{capability_id}' "
                f"(allowed_actions={self.permissions.allowed_actions})"
            )
        return self._executor.executar(capability_id, entrada, contexto)

    def health_check(self) -> HealthStatus:
        return self._executor.health_check()

    def transicionar(self, novo_status: StatusOperador) -> None:
        """Vol.IV Cap.15, secao 15.7 — máquina de estados do ciclo de vida."""
        if novo_status not in _TRANSICOES_VALIDAS.get(self.status, set()):
            raise TransicaoDeCicloInvalida(
                f"Operador '{self.id}' não pode ir de '{self.status.value}' "
                f"para '{novo_status.value}'"
            )
        self.status = novo_status
