"""Testes do Scheduler (Vol.II Cap.10, secao 10.3) — AT-10.2, AT-10.3."""

from __future__ import annotations

from datetime import timedelta

from batman_os.foundation.types import (
    CapabilityId,
    CapabilityRef,
    MissionId,
    PlanId,
    Timestamp,
    WorkflowRunId,
    agora,
)
from batman_os.kernel.planning_engine import ExecutionPlan, PlanStep
from batman_os.kernel.scheduler import Scheduler
from batman_os.kernel.workflow_engine import ResultadoInvocacao, WorkflowEngine

MISSAO = MissionId("m-1")


def _ref(nome: str) -> CapabilityRef:
    return CapabilityRef(capability_id=CapabilityId(nome), versao="1.0.0")


class _RelogioFalso:
    """Relogio controlavel manualmente — evita testes de aging dependentes
    de tempo real (lentos/instaveis)."""

    def __init__(self) -> None:
        self._agora = agora()

    def __call__(self) -> Timestamp:
        return self._agora

    def avancar(self, segundos: float) -> None:
        self._agora = self._agora + timedelta(seconds=segundos)


class InvocadorSempreSucesso:
    def invocar(self, step: PlanStep) -> ResultadoInvocacao:
        del step
        return ResultadoInvocacao(sucesso=True)


class TestAT102NuncaDespachaAntesDeDependenciasSatisfeitas:
    def test_scheduler_so_recebe_steps_que_workflow_engine_marcou_prontos(self) -> None:
        step_a = PlanStep(capability=_ref("cap-a"))
        step_b = PlanStep(capability=_ref("cap-b"), depende_de=[step_a.id])
        plano = ExecutionPlan(
            id=PlanId("p-1"),
            mission_id=MISSAO,
            steps=[step_a, step_b],
            decision_points=[],
            plan_hash="h",
        )
        wf = WorkflowEngine(InvocadorSempreSucesso())
        run = wf.iniciar(MISSAO, plano)
        scheduler = Scheduler(capacidade_worker_pool=10)

        # Antes de step_a concluir, so ele esta pronto — step_b nunca chega
        # ao scheduler (e o workflow engine quem decide o que enfileirar).
        for step in wf.passos_prontos(run.id):
            scheduler.enqueue(step, run.id, priority=1)

        despachados = scheduler.despachar_proximos()
        assert [s.id for s in despachados] == [step_a.id]

        wf.executar_passo(run.id, step_a)
        for step in wf.passos_prontos(run.id):
            scheduler.enqueue(step, run.id, priority=1)

        despachados_2 = scheduler.despachar_proximos()
        assert [s.id for s in despachados_2] == [step_b.id]


class TestAT103AgingPrevineStarvation:
    def test_step_de_prioridade_baixa_eventualmente_e_despachado(self) -> None:
        relogio = _RelogioFalso()
        scheduler = Scheduler(
            capacidade_worker_pool=1, incremento_aging_por_segundo=1.0, relogio=relogio
        )
        step_baixa = PlanStep(capability=_ref("baixa-prioridade"))
        scheduler.enqueue(step_baixa, WorkflowRunId("run-baixa"), priority=1)

        # Continuamente chegam steps de prioridade alta, mas o Worker Pool
        # so processa 1 por vez (capacidade=1) — sem aging, o de baixa
        # prioridade nunca seria escolhido.
        for i in range(5):
            step_alta = PlanStep(capability=_ref(f"alta-{i}"))
            scheduler.enqueue(step_alta, WorkflowRunId(f"run-alta-{i}"), priority=10)
            relogio.avancar(1.0)
            despachado = scheduler.despachar_proximos()
            assert despachado[0].id == step_alta.id  # prioridade alta ainda vence

        relogio.avancar(20.0)  # aging acumulado o suficiente para superar prioridade=10
        despachado_final = scheduler.despachar_proximos()
        assert despachado_final[0].id == step_baixa.id

    def test_sem_aging_prioridade_baixa_fica_starving(self) -> None:
        relogio = _RelogioFalso()
        scheduler = Scheduler(
            capacidade_worker_pool=1, incremento_aging_por_segundo=0.0, relogio=relogio
        )
        step_baixa = PlanStep(capability=_ref("baixa"))
        scheduler.enqueue(step_baixa, WorkflowRunId("run-baixa"), priority=1)

        for i in range(5):
            step_alta = PlanStep(capability=_ref(f"alta-{i}"))
            scheduler.enqueue(step_alta, WorkflowRunId(f"run-alta-{i}"), priority=10)
            relogio.avancar(100.0)
            despachado = scheduler.despachar_proximos()
            assert despachado[0].id == step_alta.id

        assert scheduler.get_queue_depth() == 1  # step_baixa ainda parado na fila


def test_cancel_remove_entradas_do_workflow_run() -> None:
    scheduler = Scheduler(capacidade_worker_pool=10)
    step = PlanStep(capability=_ref("cap-a"))
    run_id = WorkflowRunId("run-1")
    scheduler.enqueue(step, run_id, priority=5)

    assert scheduler.get_queue_depth() == 1
    scheduler.cancel(run_id)
    assert scheduler.get_queue_depth() == 0

    # enfileiramento posterior para o mesmo run cancelado e ignorado
    scheduler.enqueue(step, run_id, priority=5)
    assert scheduler.get_queue_depth() == 0


def test_despachar_respeita_capacidade_do_worker_pool() -> None:
    scheduler = Scheduler(capacidade_worker_pool=2)
    for i in range(5):
        scheduler.enqueue(
            PlanStep(capability=_ref(f"cap-{i}")), WorkflowRunId(f"run-{i}"), priority=1
        )

    despachados = scheduler.despachar_proximos()

    assert len(despachados) == 2
    assert scheduler.get_queue_depth() == 3
