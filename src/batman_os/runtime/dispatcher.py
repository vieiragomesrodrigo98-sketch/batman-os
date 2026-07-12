"""Vol. II, Cap. 10 — dispatcher real do Scheduler.

Fase 2 do roadmap de plataforma (`.claude/plans/peaceful-wondering-hearth.md`,
Estágio 2.4). O `Scheduler`/`SchedulerComFairnessPorTenant` (`kernel/
scheduler.py`, `runtime/concurrency.py`) já existiam e já eram testados
isoladamente, mas nunca instanciados fora de `tests/` — são puros seletores
(`despachar_proximos()`/`despachar_proximo()` retornam `list[PlanStep]`,
nunca executam nada). Este módulo é quem de fato conecta a seleção à
execução: despacha os passos prontos de uma ou mais `WorkflowRun`s em
PARALELO de verdade via `ThreadPoolExecutor`, usando `WorkflowEngine.
executar_passo()` (seguro para chamada concorrente desde o Estágio 2.4 —
ver `kernel/workflow_engine.py`) e `ExecutionEngine.submit()` por baixo dele
(não-bloqueante desde o Estágio 2.3).

`despachar_proximos()`/`despachar_proximo()` devolvem `PlanStep`s sem
identificar a que `WorkflowRun` cada um pertence (a fila do Scheduler é
agnóstica a isso por design, Vol.II Cap.10 secao 10.3) — este módulo mantém
o mapeamento `StepId -> WorkflowRunId` no momento de enfileirar, para poder
rotear cada passo despachado ao `executar_passo(run_id, step)` correto.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass

from batman_os.foundation.types import StepId, TenantId, WorkflowRunId
from batman_os.kernel.planning_engine import PlanStep
from batman_os.kernel.scheduler import Priority, Scheduler
from batman_os.kernel.workflow_engine import WorkflowEngine
from batman_os.runtime.concurrency import SchedulerComFairnessPorTenant

_ESTADOS_TERMINAIS_RUN = frozenset({"completed", "failed", "cancelled"})


@dataclass(frozen=True)
class RunAcompanhada:
    """Uma `WorkflowRun` sob gestão do dispatcher — `prioridade` alimenta o
    `Scheduler` simples. `tenant_id` obrigatório desde a Fase 9 (Estágio
    9.1, `.claude/plans/peaceful-wondering-hearth.md`) — antes era
    opcional (só `despachar_ate_terminal_com_fairness` exigia, via
    checagem em runtime); agora `WorkflowEngine.executar_passo()` também
    exige `tenant_id`, então as duas funções deste módulo precisam dele."""

    run_id: WorkflowRunId
    tenant_id: TenantId
    prioridade: Priority = 0


def despachar_ate_terminal(
    workflow: WorkflowEngine,
    scheduler: Scheduler,
    runs: list[RunAcompanhada],
    max_workers: int = 4,
) -> None:
    """Roda todas as `runs` até estado terminal, usando um `Scheduler`
    (prioridade + aging, Vol.II Cap.10 secao 10.3) para decidir a ordem de
    despacho quando há mais passos prontos do que capacidade concorrente.
    Cada rodada: enfileira todo passo pronto ainda não visto, despacha até
    a capacidade do Scheduler, executa o lote em paralelo, espera o lote
    inteiro concluir antes da próxima rodada (passos recém-desbloqueados só
    aparecem em `passos_prontos()` depois que suas dependências terminam)."""
    mapa_step_para_run: dict[StepId, WorkflowRunId] = {}
    pendentes = {r.run_id: r for r in runs}

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        while pendentes:
            for acompanhada in list(pendentes.values()):
                for step in workflow.passos_prontos(acompanhada.run_id):
                    if step.id not in mapa_step_para_run:
                        scheduler.enqueue(step, acompanhada.run_id, acompanhada.prioridade)
                        mapa_step_para_run[step.id] = acompanhada.run_id

            despachados = scheduler.despachar_proximos()
            if not despachados:
                break  # nada pronto e nada na fila -> ninguem mais progride sozinho

            futuros = [
                pool.submit(
                    workflow.executar_passo,
                    mapa_step_para_run[step.id],
                    step,
                    pendentes[mapa_step_para_run[step.id]].tenant_id,
                )
                for step in despachados
            ]
            wait(futuros)

            pendentes = {
                run_id: r
                for run_id, r in pendentes.items()
                if workflow.get_run(run_id).estado not in _ESTADOS_TERMINAIS_RUN
            }


def despachar_ate_terminal_com_fairness(
    workflow: WorkflowEngine,
    scheduler: SchedulerComFairnessPorTenant,
    runs: list[RunAcompanhada],
    max_workers: int = 4,
) -> None:
    """Mesma lógica de `despachar_ate_terminal`, usando
    `SchedulerComFairnessPorTenant` (weighted round-robin entre tenants,
    Vol.III Cap.14 secao 14.5) em vez do `Scheduler` simples. Cada
    `despachar_proximo()` devolve o lote de UM tenant só; para aproveitar
    `max_workers` de concorrência dentro de uma rodada, acumula lotes de
    tenants sucessivos (cada escolha já respeitando o weighted round-robin)
    até atingir a capacidade ou a fila esvaziar."""
    mapa_step_para_run: dict[StepId, WorkflowRunId] = {}
    pendentes = {r.run_id: r for r in runs}

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        while pendentes:
            for acompanhada in list(pendentes.values()):
                for step in workflow.passos_prontos(acompanhada.run_id):
                    if step.id not in mapa_step_para_run:
                        scheduler.enqueue(
                            acompanhada.tenant_id, step, acompanhada.run_id, acompanhada.prioridade
                        )
                        mapa_step_para_run[step.id] = acompanhada.run_id

            despachados_da_rodada: list[PlanStep] = []
            while len(despachados_da_rodada) < max_workers:
                resultado = scheduler.despachar_proximo()
                if resultado is None:
                    break
                _tenant, passos = resultado
                despachados_da_rodada.extend(passos)

            if not despachados_da_rodada:
                break

            futuros = [
                pool.submit(
                    workflow.executar_passo,
                    mapa_step_para_run[step.id],
                    step,
                    pendentes[mapa_step_para_run[step.id]].tenant_id,
                )
                for step in despachados_da_rodada
            ]
            wait(futuros)

            pendentes = {
                run_id: r
                for run_id, r in pendentes.items()
                if workflow.get_run(run_id).estado not in _ESTADOS_TERMINAIS_RUN
            }
