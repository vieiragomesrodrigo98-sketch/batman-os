"""Testes de `ExecutorViaImplementacoes` (roteador capability_id -> handler)."""

from __future__ import annotations

from typing import Any

import pytest

from batman_os.capabilities.capability_contract import CapabilityImplementation
from batman_os.capabilities.operator import ExecutionContext
from batman_os.foundation.types import CapabilityId, MissionId, StepId, TenantId, agora
from batman_os.orchestration.implementation_registry import (
    CapabilityNaoImplementada,
    ExecutorViaImplementacoes,
)
from batman_os.runtime.capability_engine import CapabilityDefinition, SideEffects


def _contexto() -> ExecutionContext:
    return ExecutionContext(
        mission_id=MissionId("m-1"),
        tenant_id=TenantId("t-1"),
        step_id=StepId("s-1"),
        deadline=agora(),
    )


def _handler(entrada: Any, contexto: ExecutionContext) -> Any:
    del contexto
    return {"recebido": entrada}


def _implementacao(capability_id: str) -> CapabilityImplementation:
    return CapabilityImplementation(
        definition=CapabilityDefinition(
            id=CapabilityId(capability_id),
            name=capability_id,
            version="1.0.0",
            deterministic=True,
            side_effects=SideEffects.NONE,
        ),
        handler=_handler,
    )


class TestExecutorViaImplementacoes:
    def test_roteia_para_o_handler_certo(self) -> None:
        executor = ExecutorViaImplementacoes(
            {
                CapabilityId("cap-a"): _implementacao("cap-a"),
                CapabilityId("cap-b"): _implementacao("cap-b"),
            }
        )

        saida = executor.executar(CapabilityId("cap-a"), {"x": 1}, _contexto())

        assert saida == {"recebido": {"x": 1}}

    def test_levanta_excecao_para_capability_nao_implementada(self) -> None:
        executor = ExecutorViaImplementacoes({})

        with pytest.raises(CapabilityNaoImplementada):
            executor.executar(CapabilityId("inexistente"), {}, _contexto())

    def test_health_check_sempre_saudavel(self) -> None:
        executor = ExecutorViaImplementacoes({})

        assert executor.health_check().saudavel is True
