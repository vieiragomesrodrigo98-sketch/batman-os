"""Testes de Concorrência e Isolamento (Vol.III Cap.14) — AT-14.1 a AT-14.3."""

from __future__ import annotations

from collections import Counter

from batman_os.foundation.types import (
    CapabilityId,
    CapabilityRef,
    CognitiveDebtFlag,
    DecisionPointId,
    MissionId,
    MissionTypeId,
    PlanId,
    TenantId,
    WorkflowRunId,
)
from batman_os.kernel.mission_runtime import MissionState
from batman_os.kernel.planning_engine import ExecutionPlan, PlanStep
from batman_os.kernel.workflow_engine import ResultadoInvocacao, WorkflowEngine
from batman_os.runtime.concurrency import SchedulerComFairnessPorTenant, TenantQuotas
from batman_os.runtime.operational_memory import (
    DecisionSummary,
    OperationalMemory,
    OperationalRecord,
)

TENANT_A = TenantId("tenant-a")
TENANT_B = TenantId("tenant-b")


def _ref(nome: str) -> CapabilityRef:
    return CapabilityRef(capability_id=CapabilityId(nome), versao="1.0.0")


class TestAT141IsolamentoDeDadosNaOperationalMemory:
    def test_consulta_de_um_tenant_nunca_retorna_dados_de_outro(self) -> None:
        memory = OperationalMemory()
        memory.registrar(
            OperationalRecord(
                mission_id=MissionId("m-a"),
                tenant_id=TENANT_A,
                mission_type=MissionTypeId("investigate-incident"),
                decision_points_resolved=(
                    DecisionSummary(
                        decision_point_id=DecisionPointId("dp-1"),
                        resolved_by="human",
                        chosen_option_id="a",
                        confidence=1.0,
                    ),
                ),
                final_state=MissionState.COMPLETED,
                cognitive_debt_flag=CognitiveDebtFlag.HUMAN,
            )
        )
        memory.registrar(
            OperationalRecord(
                mission_id=MissionId("m-b"),
                tenant_id=TENANT_B,
                mission_type=MissionTypeId("investigate-incident"),
                decision_points_resolved=(
                    DecisionSummary(
                        decision_point_id=DecisionPointId("dp-1"),
                        resolved_by="human",
                        chosen_option_id="b",
                        confidence=1.0,
                    ),
                ),
                final_state=MissionState.COMPLETED,
                cognitive_debt_flag=CognitiveDebtFlag.HUMAN,
            )
        )

        historico_a = memory.get_decision_history(TENANT_A, "dp-1")
        historico_b = memory.get_decision_history(TENANT_B, "dp-1")

        assert [h.chosen_option_id for h in historico_a] == ["a"]
        assert [h.chosen_option_id for h in historico_b] == ["b"]

    def test_find_similar_missions_tambem_e_escopado_por_tenant(self) -> None:
        from batman_os.kernel.mission_runtime import MissionIntent

        memory = OperationalMemory()
        memory.registrar(
            OperationalRecord(
                mission_id=MissionId("m-a"),
                tenant_id=TENANT_A,
                mission_type=MissionTypeId("investigate-incident"),
                final_state=MissionState.COMPLETED,
                cognitive_debt_flag=CognitiveDebtFlag.AUTONOMOUS,
            )
        )

        resultado_b = memory.find_similar_missions(TENANT_B, MissionIntent(dados={}), limit=10)
        assert resultado_b == []


class TestAT142FairnessEntreTenants:
    def test_tenant_baixo_volume_mantem_taxa_minima_sob_carga_de_tenant_grande(self) -> None:
        quotas = TenantQuotas(pesos={TENANT_A: 9.0, TENANT_B: 1.0})
        scheduler = SchedulerComFairnessPorTenant(quotas, capacidade_por_despacho=1)

        despachos: Counter[TenantId] = Counter()
        for rodada in range(100):
            scheduler.enqueue(
                TENANT_A,
                PlanStep(capability=_ref(f"a-{rodada}")),
                WorkflowRunId("run-a"),
                priority=1,
            )
            scheduler.enqueue(
                TENANT_B,
                PlanStep(capability=_ref(f"b-{rodada}")),
                WorkflowRunId("run-b"),
                priority=1,
            )
            resultado = scheduler.despachar_proximo()
            assert resultado is not None
            tenant_escolhido, _passos = resultado
            despachos[tenant_escolhido] += 1

        # Proporcao aproximada 9:1 (peso 9 vs peso 1) — nunca 100:0: o tenant
        # de baixo volume nunca fica totalmente starved.
        assert despachos[TENANT_B] >= 8
        assert despachos[TENANT_A] >= despachos[TENANT_B]

    def test_tenant_sem_itens_na_fila_nao_e_escolhido(self) -> None:
        quotas = TenantQuotas()
        scheduler = SchedulerComFairnessPorTenant(quotas)
        scheduler.enqueue(
            TENANT_A, PlanStep(capability=_ref("a")), WorkflowRunId("run-a"), priority=1
        )

        tenant_escolhido, _ = scheduler.despachar_proximo()  # type: ignore[misc]
        assert tenant_escolhido == TENANT_A

    def test_sem_nenhuma_fila_nao_ha_o_que_despachar(self) -> None:
        scheduler = SchedulerComFairnessPorTenant(TenantQuotas())
        assert scheduler.despachar_proximo() is None


class TestAT143IsolamentoDeFalhaEntreWorkflowRuns:
    def test_falha_de_um_run_nao_afeta_outro_run_concorrente(self) -> None:
        class InvocadorPorCapability:
            def invocar(self, step: PlanStep) -> ResultadoInvocacao:
                if step.capability.capability_id == "falha-proposital":
                    return ResultadoInvocacao(sucesso=False)
                return ResultadoInvocacao(sucesso=True)

        wf = WorkflowEngine(InvocadorPorCapability())

        plano_a = ExecutionPlan(
            id=PlanId("p-a"),
            mission_id=MissionId("m-a"),
            tenant_id=TENANT_A,
            steps=[PlanStep(capability=_ref("falha-proposital"))],
            decision_points=[],
            plan_hash="h-a",
        )
        plano_b = ExecutionPlan(
            id=PlanId("p-b"),
            mission_id=MissionId("m-b"),
            tenant_id=TENANT_B,
            steps=[PlanStep(capability=_ref("sucesso"))],
            decision_points=[],
            plan_hash="h-b",
        )

        run_a = wf.iniciar(MissionId("m-a"), plano_a)
        run_b = wf.iniciar(MissionId("m-b"), plano_b)

        resultado_a = wf.executar_passo(run_a.id, plano_a.steps[0])
        resultado_b = wf.executar_passo(run_b.id, plano_b.steps[0])

        assert resultado_a.estado == "failed"
        assert resultado_b.estado == "completed"
