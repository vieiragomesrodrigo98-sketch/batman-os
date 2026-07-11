"""Testes de `TabelaDeEntradasPorStep` e `InvocadorDeStepPadrao`."""

from __future__ import annotations

import pytest

from batman_os.capabilities.capability_contract import CapabilityImplementation
from batman_os.capabilities.operator import (
    FilesystemAccess,
    NetworkPolicy,
    Operator,
    PermissionSet,
    ResourceLimits,
    SandboxPolicy,
    SideEffectScope,
)
from batman_os.foundation.types import (
    CapabilityId,
    CapabilityRef,
    MissionId,
    OperatorId,
    OperatorRef,
    StepId,
    TenantId,
)
from batman_os.kernel.planning_engine import PlanStep
from batman_os.orchestration.implementation_registry import ExecutorViaImplementacoes
from batman_os.orchestration.schema_validators import (
    ValidadorContratoSempreAprova,
    ValidadorSchemaEstrutural,
)
from batman_os.orchestration.step_invoker import (
    EntradaNaoRegistrada,
    InvocadorDeStepPadrao,
    TabelaDeEntradasPorStep,
)
from batman_os.runtime.capability_engine import (
    CapabilityDefinition,
    CapabilityRegistry,
    SideEffects,
)
from batman_os.runtime.execution_engine import ExecutionEngine


class TestTabelaDeEntradasPorStep:
    def test_registra_e_recupera(self) -> None:
        tabela = TabelaDeEntradasPorStep()
        tabela.registrar(StepId("s-1"), {"x": 1})

        assert tabela.obter(StepId("s-1")) == {"x": 1}

    def test_levanta_excecao_para_step_sem_entrada(self) -> None:
        tabela = TabelaDeEntradasPorStep()

        with pytest.raises(EntradaNaoRegistrada):
            tabela.obter(StepId("desconhecido"))


def _handler_eco(entrada, contexto):  # type: ignore[no-untyped-def]
    del contexto
    return {"recebido": entrada}


class TestInvocadorDeStepPadrao:
    def test_invoca_a_capability_com_a_entrada_registrada(self) -> None:
        capability_id = CapabilityId("cap-eco")
        registry = CapabilityRegistry()
        registry.register(
            CapabilityDefinition(
                id=capability_id,
                name="cap-eco",
                version="1.0.0",
                output_schema={"properties": {"recebido": {}}},
                deterministic=True,
                side_effects=SideEffects.NONE,
            )
        )

        implementacao = CapabilityImplementation(
            definition=registry.resolve(CapabilityRef(capability_id=capability_id, versao="1.0.0")),
            handler=_handler_eco,
        )
        operator = Operator(
            operator_id=OperatorId("op-1"),
            capabilities=[capability_id],
            permissions=PermissionSet(
                allowed_actions=[str(capability_id)], side_effect_scope=SideEffectScope.READ_ONLY
            ),
            sandbox=SandboxPolicy(
                resource_limits=ResourceLimits(),
                network_policy=NetworkPolicy.NONE,
                filesystem_access=FilesystemAccess.NONE,
            ),
            executor=ExecutorViaImplementacoes({capability_id: implementacao}),
        )
        engine = ExecutionEngine(
            validador_schema=ValidadorSchemaEstrutural(),
            validador_contrato_nao_deterministico=ValidadorContratoSempreAprova(),
        )
        tabela = TabelaDeEntradasPorStep()
        step = PlanStep(capability=CapabilityRef(capability_id=capability_id, versao="1.0.0"))
        tabela.registrar(step.id, {"caminho": "a.py"})

        invocador = InvocadorDeStepPadrao(
            execution_engine=engine,
            operator=operator,
            operator_ref=OperatorRef(operator_id=OperatorId("op-1")),
            capability_registry=registry,
            tabela_entradas=tabela,
            mission_id=MissionId("m-1"),
            tenant_id=TenantId("t-1"),
        )

        resultado = invocador.invocar(step)

        assert resultado.sucesso is True
        assert resultado.output == {"recebido": {"caminho": "a.py"}}
        engine.fechar()

    def test_levanta_erro_se_entrada_nao_foi_registrada(self) -> None:
        capability_id = CapabilityId("cap-eco")
        registry = CapabilityRegistry()
        registry.register(
            CapabilityDefinition(
                id=capability_id,
                name="cap-eco",
                version="1.0.0",
                deterministic=True,
                side_effects=SideEffects.NONE,
            )
        )
        operator = Operator(
            operator_id=OperatorId("op-1"),
            capabilities=[capability_id],
            permissions=PermissionSet(
                allowed_actions=[str(capability_id)], side_effect_scope=SideEffectScope.READ_ONLY
            ),
            sandbox=SandboxPolicy(
                resource_limits=ResourceLimits(),
                network_policy=NetworkPolicy.NONE,
                filesystem_access=FilesystemAccess.NONE,
            ),
            executor=ExecutorViaImplementacoes({}),
        )
        engine = ExecutionEngine(
            validador_schema=ValidadorSchemaEstrutural(),
            validador_contrato_nao_deterministico=ValidadorContratoSempreAprova(),
        )
        invocador = InvocadorDeStepPadrao(
            execution_engine=engine,
            operator=operator,
            operator_ref=OperatorRef(operator_id=OperatorId("op-1")),
            capability_registry=registry,
            tabela_entradas=TabelaDeEntradasPorStep(),
            mission_id=MissionId("m-1"),
            tenant_id=TenantId("t-1"),
        )
        step = PlanStep(capability=CapabilityRef(capability_id=capability_id, versao="1.0.0"))

        with pytest.raises(EntradaNaoRegistrada):
            invocador.invocar(step)
        engine.fechar()
