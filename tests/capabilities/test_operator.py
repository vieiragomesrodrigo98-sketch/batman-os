"""Testes do Operador (Vol.IV Cap.15) — AT-15.1 a AT-15.3."""

from __future__ import annotations

from typing import Any

import pytest

from batman_os.capabilities.operator import (
    ExecutionContext,
    FilesystemAccess,
    HealthStatus,
    NetworkPolicy,
    Operator,
    PermissaoNegada,
    PermissionSet,
    RegistroOperadorInvalido,
    ResourceLimits,
    SandboxPolicy,
    SideEffectScope,
    StatusOperador,
    TransicaoDeCicloInvalida,
)
from batman_os.foundation.types import CapabilityId, MissionId, OperatorId, StepId, TenantId, agora


def _contexto() -> ExecutionContext:
    return ExecutionContext(
        mission_id=MissionId("m-1"),
        tenant_id=TenantId("tenant-1"),
        step_id=StepId("s-1"),
        deadline=agora(),
    )


def _sandbox() -> SandboxPolicy:
    return SandboxPolicy(
        resource_limits=ResourceLimits(),
        network_policy=NetworkPolicy.NONE,
        filesystem_access=FilesystemAccess.NONE,
    )


class ExecutorEspiao:
    """Registra se foi chamado — usado para provar que uma acao negada
    (AT-15.1/15.2) nunca toca o mundo real."""

    def __init__(self) -> None:
        self.chamadas = 0

    def executar(
        self, capability_id: CapabilityId, entrada: Any, contexto: ExecutionContext
    ) -> Any:
        del capability_id, entrada, contexto
        self.chamadas += 1
        return {"ok": True}

    def health_check(self) -> HealthStatus:
        return HealthStatus(saudavel=True)


def _operador(
    executor: ExecutorEspiao,
    allowed_actions: list[str] | None = None,
    side_effect_scope: SideEffectScope = SideEffectScope.READ_ONLY,
    requires_approval_above: float | None = None,
) -> Operator:
    return Operator(
        operator_id=OperatorId("op-1"),
        capabilities=[CapabilityId("cap-a")],
        permissions=PermissionSet(
            allowed_actions=allowed_actions or [],
            side_effect_scope=side_effect_scope,
            requires_approval_above=requires_approval_above,
        ),
        sandbox=_sandbox(),
        executor=executor,
    )


class TestAT151NuncaExecutaForaDoAllowedActions:
    def test_acao_fora_da_whitelist_e_rejeitada_sem_tocar_o_executor(self) -> None:
        executor = ExecutorEspiao()
        operador = _operador(executor, allowed_actions=["outra-capability"])

        with pytest.raises(PermissaoNegada):
            operador.execute(CapabilityId("cap-a"), {}, _contexto())

        assert executor.chamadas == 0

    def test_acao_na_whitelist_e_permitida(self) -> None:
        executor = ExecutorEspiao()
        operador = _operador(executor, allowed_actions=["cap-a"])

        resultado = operador.execute(CapabilityId("cap-a"), {}, _contexto())

        assert resultado == {"ok": True}
        assert executor.chamadas == 1

    def test_allowed_actions_vazio_por_padrao_menor_privilegio(self) -> None:
        executor = ExecutorEspiao()
        operador = _operador(executor)  # allowed_actions nao informado

        assert operador.permissions.allowed_actions == []
        with pytest.raises(PermissaoNegada):
            operador.execute(CapabilityId("cap-a"), {}, _contexto())


class TestAT152QuarentenaRejeitaNovasExecucoes:
    def test_operador_em_quarentena_rejeita_mesmo_com_permissao(self) -> None:
        executor = ExecutorEspiao()
        operador = _operador(executor, allowed_actions=["cap-a"])
        operador.transicionar(StatusOperador.CERTIFIED)
        operador.transicionar(StatusOperador.ACTIVE)
        operador.transicionar(StatusOperador.QUARANTINED)

        with pytest.raises(PermissaoNegada):
            operador.execute(CapabilityId("cap-a"), {}, _contexto())

        assert executor.chamadas == 0

    def test_operador_reativado_volta_a_executar(self) -> None:
        executor = ExecutorEspiao()
        operador = _operador(executor, allowed_actions=["cap-a"])
        operador.transicionar(StatusOperador.CERTIFIED)
        operador.transicionar(StatusOperador.ACTIVE)
        operador.transicionar(StatusOperador.QUARANTINED)
        operador.transicionar(StatusOperador.ACTIVE)

        resultado = operador.execute(CapabilityId("cap-a"), {}, _contexto())
        assert resultado == {"ok": True}

    def test_transicao_fora_do_diagrama_e_rejeitada(self) -> None:
        executor = ExecutorEspiao()
        operador = _operador(executor)

        with pytest.raises(TransicaoDeCicloInvalida):
            operador.transicionar(StatusOperador.ACTIVE)  # pula Certified


class TestAT153IrreversibleWriteExigeApprovalThreshold:
    def test_irreversible_sem_threshold_e_rejeitado_no_registro(self) -> None:
        with pytest.raises(RegistroOperadorInvalido):
            _operador(
                ExecutorEspiao(),
                side_effect_scope=SideEffectScope.IRREVERSIBLE_WRITE,
                requires_approval_above=None,
            )

    def test_irreversible_com_threshold_funciona(self) -> None:
        operador = _operador(
            ExecutorEspiao(),
            side_effect_scope=SideEffectScope.IRREVERSIBLE_WRITE,
            requires_approval_above=0.8,
        )
        assert operador.permissions.requires_approval_above == 0.8

    def test_reversible_nao_exige_threshold(self) -> None:
        operador = _operador(ExecutorEspiao(), side_effect_scope=SideEffectScope.REVERSIBLE_WRITE)
        assert operador.permissions.requires_approval_above is None
