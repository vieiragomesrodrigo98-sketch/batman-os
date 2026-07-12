"""Testes de Cooperação entre Operadores (Vol.IV Cap.19) — AT-19.1 a AT-19.3."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from batman_os.capabilities.cooperation import (
    ReferenciaDiretaEntreOperadoresDetectada,
    auditar_ausencia_de_referencia_direta,
    criar_submissao,
)
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
from batman_os.foundation.types import (
    CapabilityId,
    CapabilityRef,
    Criticidade,
    EscalationPolicy,
    MissionId,
    MissionTypeId,
    OperatorId,
    Reversibilidade,
    TenantId,
)
from batman_os.kernel.event_bus import EventBus
from batman_os.kernel.mission_runtime import MissionIntent, MissionRuntime
from batman_os.kernel.planning_engine import PlanStep
from batman_os.kernel.workflow_engine import ResultadoInvocacao, WorkflowEngine
from batman_os.workflow.missions import MissionTypeDefinition, MissionTypeRegistry

TIPO_PREPARAR_DEPLOY = MissionTypeId("preparar-deploy")
TIPO_RODAR_TESTES = MissionTypeId("rodar-testes")


def _registro_tipos() -> MissionTypeRegistry:
    registro = MissionTypeRegistry()
    politica = EscalationPolicy(
        confidence_threshold=0.7,
        preferred_escalation="human",
        max_llm_retries=1,
        reversibility=Reversibilidade.REVERSIVEL,
    )
    for tipo in (TIPO_PREPARAR_DEPLOY, TIPO_RODAR_TESTES):
        registro.register(
            MissionTypeDefinition(
                id=tipo,
                criticality=Criticidade.MEDIUM,
                default_sla=timedelta(hours=1),
                escalation_defaults=politica,
            )
        )
    return registro


class ExecutorSimples:
    def executar(
        self, capability_id: CapabilityId, entrada: Any, contexto: ExecutionContext
    ) -> Any:
        del capability_id, entrada, contexto
        return {"ok": True}

    def health_check(self) -> HealthStatus:
        return HealthStatus(saudavel=True)


def _sandbox() -> SandboxPolicy:
    return SandboxPolicy(
        resource_limits=ResourceLimits(),
        network_policy=NetworkPolicy.NONE,
        filesystem_access=FilesystemAccess.NONE,
    )


def _operador(operator_id: str = "op-1") -> Operator:
    return Operator(
        operator_id=OperatorId(operator_id),
        capabilities=[CapabilityId("cap-a")],
        permissions=PermissionSet(
            allowed_actions=["cap-a"], side_effect_scope=SideEffectScope.READ_ONLY
        ),
        sandbox=_sandbox(),
        executor=ExecutorSimples(),
    )


class TestAT191NenhumOperadorTemReferenciaDireta:
    def test_operador_normal_passa_na_auditoria(self) -> None:
        operador = _operador()
        auditar_ausencia_de_referencia_direta(operador)  # nao levanta

    def test_operador_com_referencia_direta_e_detectado(self) -> None:
        operador_a = _operador("op-a")
        operador_b = _operador("op-b")
        operador_a._outro = operador_b  # type: ignore[attr-defined]  # simula violacao

        with pytest.raises(ReferenciaDiretaEntreOperadoresDetectada):
            auditar_ausencia_de_referencia_direta(operador_a)

    def test_referencia_dentro_de_lista_tambem_e_detectada(self) -> None:
        operador_a = _operador("op-a")
        operador_b = _operador("op-b")
        operador_a._outros = [operador_b]  # type: ignore[attr-defined]

        with pytest.raises(ReferenciaDiretaEntreOperadoresDetectada):
            auditar_ausencia_de_referencia_direta(operador_a)

    def test_execution_context_nunca_referencia_operador(self) -> None:
        """ExecutionContext (Cap.15, secao 15.3) so carrega IDs/timestamps —
        nunca pode, por construcao de tipo, carregar um Operator."""
        campos = ExecutionContext.model_fields
        assert "operator" not in campos
        assert "operador" not in campos


class TestAT192FanInAguardaTodosOsPredecessores:
    def test_step_consolidador_so_fica_pronto_apos_todos_os_predecessores(self) -> None:
        coletar = PlanStep(
            capability=CapabilityRef(capability_id=CapabilityId("coletar"), versao="1.0.0")
        )
        cpu = PlanStep(
            capability=CapabilityRef(capability_id=CapabilityId("cpu"), versao="1.0.0"),
            depende_de=[coletar.id],
        )
        memoria = PlanStep(
            capability=CapabilityRef(capability_id=CapabilityId("memoria"), versao="1.0.0"),
            depende_de=[coletar.id],
        )
        consolidar = PlanStep(
            capability=CapabilityRef(capability_id=CapabilityId("consolidar"), versao="1.0.0"),
            depende_de=[cpu.id, memoria.id],
        )

        from batman_os.foundation.types import PlanId
        from batman_os.kernel.planning_engine import ExecutionPlan

        plano = ExecutionPlan(
            id=PlanId("p-1"),
            mission_id=MissionId("m-1"),
            tenant_id=TenantId("t-1"),
            steps=[coletar, cpu, memoria, consolidar],
            decision_points=[],
            plan_hash="h",
        )

        wf = WorkflowEngine(_InvocadorSempreSucesso())
        run = wf.iniciar(MissionId("m-1"), plano)

        assert consolidar not in wf.passos_prontos(run.id)

        wf.executar_passo(run.id, coletar, TenantId("t-1"))
        assert consolidar not in wf.passos_prontos(run.id)
        assert cpu in wf.passos_prontos(run.id)
        assert memoria in wf.passos_prontos(run.id)

        wf.executar_passo(run.id, cpu, TenantId("t-1"))
        assert consolidar not in wf.passos_prontos(run.id)  # memoria ainda nao concluiu

        wf.executar_passo(run.id, memoria, TenantId("t-1"))
        assert consolidar in wf.passos_prontos(run.id)


class _InvocadorSempreSucesso:
    def invocar(self, step: PlanStep) -> ResultadoInvocacao:
        del step
        return ResultadoInvocacao(sucesso=True)


class TestAT193SubmissaoHerdaTenantDaMissaoPai:
    def test_submissao_herda_tenant_id_do_pai(self) -> None:
        runtime = MissionRuntime(EventBus(), tipos=_registro_tipos())
        pai = runtime.create(
            MissionIntent(dados={}),
            TIPO_PREPARAR_DEPLOY,
            tenant_id=TenantId("tenant-x"),
        )

        filha = criar_submissao(
            runtime,
            pai,
            MissionIntent(dados={"etapa": "rodar-testes"}),
            TIPO_RODAR_TESTES,
        )

        assert filha.tenant_id == pai.tenant_id
        assert filha.parent_mission_id == pai.id

    def test_submissao_e_auditavel_independentemente_via_replay(self) -> None:
        event_bus = EventBus()
        runtime = MissionRuntime(event_bus, tipos=_registro_tipos())
        pai = runtime.create(
            MissionIntent(dados={}),
            TIPO_PREPARAR_DEPLOY,
            tenant_id=TenantId("tenant-x"),
        )
        filha = criar_submissao(runtime, pai, MissionIntent(dados={}), TIPO_RODAR_TESTES)

        historia_pai = event_bus.replay(pai.id)
        historia_filha = event_bus.replay(filha.id)

        assert len(historia_pai) == 1  # so o MissionCreated do pai
        assert len(historia_filha) == 1  # so o MissionCreated da filha, isolado
        assert historia_filha[0].mission_id == filha.id
