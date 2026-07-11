"""Testes de `OperadorExecutavelAdapter` (Operator de 3 args -> OperadorExecutavel de 2)."""

from __future__ import annotations

from typing import Any

from batman_os.capabilities.operator import (
    ExecutionContext,
    FilesystemAccess,
    HealthStatus,
    NetworkPolicy,
    Operator,
    PermissionSet,
    ResourceLimits,
    SandboxPolicy,
    SideEffectScope,
)
from batman_os.foundation.types import CapabilityId, MissionId, OperatorId, StepId, TenantId, agora
from batman_os.orchestration.operator_bridge import OperadorExecutavelAdapter


class _ExecutorFake:
    def __init__(self) -> None:
        self.chamadas: list[tuple[CapabilityId, Any, ExecutionContext]] = []

    def executar(
        self, capability_id: CapabilityId, entrada: Any, contexto: ExecutionContext
    ) -> Any:
        self.chamadas.append((capability_id, entrada, contexto))
        return {"ok": True}

    def health_check(self) -> HealthStatus:
        return HealthStatus(saudavel=True)


def _contexto() -> ExecutionContext:
    return ExecutionContext(
        mission_id=MissionId("m-1"),
        tenant_id=TenantId("t-1"),
        step_id=StepId("s-1"),
        deadline=agora(),
    )


def _operator(executor: _ExecutorFake, capability_id: str = "cap-a") -> Operator:
    return Operator(
        operator_id=OperatorId("op-1"),
        capabilities=[CapabilityId(capability_id)],
        permissions=PermissionSet(
            allowed_actions=[capability_id], side_effect_scope=SideEffectScope.READ_ONLY
        ),
        sandbox=SandboxPolicy(
            resource_limits=ResourceLimits(),
            network_policy=NetworkPolicy.NONE,
            filesystem_access=FilesystemAccess.NONE,
        ),
        executor=executor,
    )


class TestOperadorExecutavelAdapter:
    def test_encaminha_para_operator_execute_com_o_contexto_do_construtor(self) -> None:
        executor = _ExecutorFake()
        contexto = _contexto()
        adapter = OperadorExecutavelAdapter(_operator(executor), contexto)

        saida = adapter.executar(CapabilityId("cap-a"), {"x": 1})

        assert saida == {"ok": True}
        assert executor.chamadas == [(CapabilityId("cap-a"), {"x": 1}, contexto)]

    def test_health_check_delega_ao_operator(self) -> None:
        adapter = OperadorExecutavelAdapter(_operator(_ExecutorFake()), _contexto())

        assert adapter.health_check().saudavel is True

    def test_dois_adapters_com_contextos_diferentes_nao_vazam_estado(self) -> None:
        """Fase 2 do roadmap de plataforma (`.claude/plans/peaceful-
        wondering-hearth.md`), Estagio 2.3 — contexto e imutavel por
        instancia; dois adapters concorrentes sobre o mesmo Operator nunca
        podem ver o contexto um do outro (o bug que definir_contexto()
        mutavel permitia antes desta mudanca)."""
        executor = _ExecutorFake()
        operator = _operator(executor)
        contexto_a = _contexto()
        contexto_b = ExecutionContext(
            mission_id=MissionId("m-2"),
            tenant_id=TenantId("t-2"),
            step_id=StepId("s-2"),
            deadline=agora(),
        )
        adapter_a = OperadorExecutavelAdapter(operator, contexto_a)
        adapter_b = OperadorExecutavelAdapter(operator, contexto_b)

        adapter_b.executar(CapabilityId("cap-a"), {"y": 2})
        adapter_a.executar(CapabilityId("cap-a"), {"x": 1})

        assert executor.chamadas == [
            (CapabilityId("cap-a"), {"y": 2}, contexto_b),
            (CapabilityId("cap-a"), {"x": 1}, contexto_a),
        ]
