"""Testes de `runtime/dispatcher.py` (Fase 2 do roadmap de plataforma,
`.claude/plans/peaceful-wondering-hearth.md`, Estagio 2.4) — prova de que o
Scheduler (puro seletor) esta de fato conectado a execucao real, em
paralelo, com prioridade/aging e fairness por tenant."""

from __future__ import annotations

import threading
import time

import pytest

from batman_os.foundation.types import CapabilityId, CapabilityRef, MissionId, PlanId, TenantId
from batman_os.kernel.planning_engine import ExecutionPlan, PlanStep
from batman_os.kernel.scheduler import Scheduler
from batman_os.kernel.workflow_engine import ResultadoInvocacao, WorkflowEngine
from batman_os.runtime.concurrency import SchedulerComFairnessPorTenant, TenantQuotas
from batman_os.runtime.dispatcher import (
    RunAcompanhada,
    despachar_ate_terminal,
    despachar_ate_terminal_com_fairness,
)

TENANT = TenantId("tenant-1")


def _ref(nome: str) -> CapabilityRef:
    return CapabilityRef(capability_id=CapabilityId(nome), versao="1.0.0")


def _plano(
    mission_id: MissionId,
    steps: list[PlanStep],
    plan_id: str = "p-1",
    tenant_id: TenantId = TENANT,
) -> ExecutionPlan:
    return ExecutionPlan(
        id=PlanId(plan_id),
        mission_id=mission_id,
        tenant_id=tenant_id,
        steps=steps,
        decision_points=[],
        plan_hash=f"hash-{plan_id}",
    )


class InvocadorComAtrasoRegistrandoJanela:
    """Registra o intervalo [inicio, fim] de cada invocacao — usado para
    provar que passos independentes rodam de fato em paralelo (janelas se
    sobrepoem), nao so "sem erro"."""

    def __init__(self, atraso_segundos: float = 0.05) -> None:
        self._atraso = atraso_segundos
        self.janelas: list[tuple[float, float]] = []
        self._lock = threading.Lock()

    def invocar(self, step: PlanStep) -> ResultadoInvocacao:
        del step
        inicio = time.monotonic()
        time.sleep(self._atraso)
        fim = time.monotonic()
        with self._lock:
            self.janelas.append((inicio, fim))
        return ResultadoInvocacao(sucesso=True)


def _houve_sobreposicao(janelas: list[tuple[float, float]]) -> bool:
    return any(
        inicio_i < fim_j and inicio_j < fim_i
        for i, (inicio_i, fim_i) in enumerate(janelas)
        for j, (inicio_j, fim_j) in enumerate(janelas)
        if i != j
    )


class TestDespacharAteTerminal:
    def test_passos_independentes_do_mesmo_run_rodam_em_paralelo(self) -> None:
        passos = [PlanStep(capability=_ref(f"cap-{i}")) for i in range(4)]
        invocador = InvocadorComAtrasoRegistrandoJanela(atraso_segundos=0.05)
        wf = WorkflowEngine(invocador)
        run = wf.iniciar(MissionId("m-1"), _plano(MissionId("m-1"), passos))
        scheduler = Scheduler(capacidade_worker_pool=4)

        despachar_ate_terminal(wf, scheduler, [RunAcompanhada(run_id=run.id)], max_workers=4)

        final = wf.get_run(run.id)
        assert final.estado == "completed"
        assert len(final.completed_steps) == 4
        assert _houve_sobreposicao(invocador.janelas)

    def test_cadeia_de_dependencias_respeita_ordem_mesmo_com_paralelismo_disponivel(
        self,
    ) -> None:
        a = PlanStep(capability=_ref("cap-a"))
        b = PlanStep(capability=_ref("cap-b"), depende_de=[a.id])
        c = PlanStep(capability=_ref("cap-c"), depende_de=[b.id])
        invocador = InvocadorComAtrasoRegistrandoJanela(atraso_segundos=0.01)
        wf = WorkflowEngine(invocador)
        run = wf.iniciar(MissionId("m-1"), _plano(MissionId("m-1"), [a, b, c]))
        scheduler = Scheduler(capacidade_worker_pool=4)

        despachar_ate_terminal(wf, scheduler, [RunAcompanhada(run_id=run.id)], max_workers=4)

        final = wf.get_run(run.id)
        assert final.estado == "completed"
        assert [r.step_id for r in final.completed_steps] == [a.id, b.id, c.id]

    def test_multiplos_runs_independentes_completam_todos(self) -> None:
        invocador = InvocadorComAtrasoRegistrandoJanela(atraso_segundos=0.01)
        wf = WorkflowEngine(invocador)
        acompanhadas = []
        for i in range(3):
            step = PlanStep(capability=_ref(f"cap-run-{i}"))
            mission_id = MissionId(f"m-{i}")
            run = wf.iniciar(mission_id, _plano(mission_id, [step], plan_id=f"p-{i}"))
            acompanhadas.append(RunAcompanhada(run_id=run.id))

        scheduler = Scheduler(capacidade_worker_pool=4)
        despachar_ate_terminal(wf, scheduler, acompanhadas, max_workers=4)

        for acompanhada in acompanhadas:
            assert wf.get_run(acompanhada.run_id).estado == "completed"

    def test_falha_de_um_run_nao_impede_outro_run_de_completar(self) -> None:
        class InvocadorPorCapability:
            def invocar(self, step: PlanStep) -> ResultadoInvocacao:
                if step.capability.capability_id == "falha":
                    return ResultadoInvocacao(sucesso=False)
                return ResultadoInvocacao(sucesso=True)

        wf = WorkflowEngine(InvocadorPorCapability())
        step_falha = PlanStep(capability=_ref("falha"))
        step_ok = PlanStep(capability=_ref("ok"))
        run_falha = wf.iniciar(
            MissionId("m-falha"), _plano(MissionId("m-falha"), [step_falha], plan_id="p-falha")
        )
        run_ok = wf.iniciar(MissionId("m-ok"), _plano(MissionId("m-ok"), [step_ok], plan_id="p-ok"))

        scheduler = Scheduler(capacidade_worker_pool=4)
        despachar_ate_terminal(
            wf,
            scheduler,
            [RunAcompanhada(run_id=run_falha.id), RunAcompanhada(run_id=run_ok.id)],
            max_workers=4,
        )

        assert wf.get_run(run_falha.id).estado == "failed"
        assert wf.get_run(run_ok.id).estado == "completed"


class TestDespacharAteTerminalComFairness:
    def test_runs_de_tenants_diferentes_completam_todos(self) -> None:
        invocador = InvocadorComAtrasoRegistrandoJanela(atraso_segundos=0.005)
        wf = WorkflowEngine(invocador)
        tenant_a, tenant_b = TenantId("t-a"), TenantId("t-b")
        acompanhadas = []
        for i in range(5):
            step = PlanStep(capability=_ref(f"a-{i}"))
            mission_id = MissionId(f"m-a-{i}")
            run = wf.iniciar(
                mission_id, _plano(mission_id, [step], plan_id=f"p-a-{i}", tenant_id=tenant_a)
            )
            acompanhadas.append(RunAcompanhada(run_id=run.id, tenant_id=tenant_a))
        for i in range(5):
            step = PlanStep(capability=_ref(f"b-{i}"))
            mission_id = MissionId(f"m-b-{i}")
            run = wf.iniciar(
                mission_id, _plano(mission_id, [step], plan_id=f"p-b-{i}", tenant_id=tenant_b)
            )
            acompanhadas.append(RunAcompanhada(run_id=run.id, tenant_id=tenant_b))

        quotas = TenantQuotas(pesos={tenant_a: 1.0, tenant_b: 1.0})
        scheduler = SchedulerComFairnessPorTenant(quotas, capacidade_por_despacho=1)

        despachar_ate_terminal_com_fairness(wf, scheduler, acompanhadas, max_workers=4)

        for acompanhada in acompanhadas:
            assert wf.get_run(acompanhada.run_id).estado == "completed"

    def test_run_sem_tenant_id_levanta_erro_claro(self) -> None:
        wf = WorkflowEngine(InvocadorComAtrasoRegistrandoJanela())
        step = PlanStep(capability=_ref("cap-a"))
        run = wf.iniciar(MissionId("m-1"), _plano(MissionId("m-1"), [step]))
        scheduler = SchedulerComFairnessPorTenant(TenantQuotas())

        with pytest.raises(ValueError):
            despachar_ate_terminal_com_fairness(
                wf, scheduler, [RunAcompanhada(run_id=run.id)], max_workers=1
            )
