"""Vol. II, Cap. 10 — Scheduler.

Decide QUANDO e EM QUE GRAU DE PARALELISMO passos de workflow (de uma ou mais
missões concorrentes) são efetivamente despachados para Operadores — nunca
decide O QUE executar (Workflow Engine) ou POR QUÊ (Decision Engine).

Fonte da verdade: docs/spec/02-kernel/06-event-bus-scheduler.md, secao 10.3
"""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel, Field

from batman_os.foundation.types import Timestamp, WorkflowRunId, agora
from batman_os.kernel.planning_engine import PlanStep

Priority = int  # maior valor = mais prioritario (ver secao 10.3.3, aging).


class _EntradaFila(BaseModel):
    """Vol.II Cap.10, secao 10.3.2 — uma entrada na fila de steps prontos."""

    step: PlanStep
    workflow_run_id: WorkflowRunId
    prioridade_base: Priority
    enfileirado_em: Timestamp = Field(default_factory=agora)

    def prioridade_efetiva(self, agora_: Timestamp, incremento_por_segundo: float) -> float:
        """Vol.II Cap.10, secao 10.5 — aging: aumento gradual de prioridade
        efetiva com o tempo de espera, para que nenhum passo de prioridade
        igual ou superior sofra starvation indefinidamente (AT-10.3)."""
        espera_segundos = (agora_ - self.enfileirado_em).total_seconds()
        return self.prioridade_base + espera_segundos * incremento_por_segundo


class Scheduler:
    """Vol.II Cap.10, secao 10.3.

    `despachar_proximos()` nao consta no contrato explicito da especificacao
    (`enqueue`/`cancel`/`getQueueDepth`), mas e necessario nesta implementacao
    de referencia para o Worker Pool ser executavel — sem ele, a fila
    acumularia entradas sem nenhum mecanismo de saida. Adicao mecanica, nao
    decisao arquitetural nova.
    """

    def __init__(
        self,
        capacidade_worker_pool: int,
        incremento_aging_por_segundo: float = 0.01,
        relogio: Callable[[], Timestamp] = agora,
    ) -> None:
        self._fila: list[_EntradaFila] = []
        self._capacidade = capacidade_worker_pool
        self._incremento_aging = incremento_aging_por_segundo
        self._relogio = relogio
        self._cancelados: set[WorkflowRunId] = set()

    def enqueue(self, step: PlanStep, workflow_run_id: WorkflowRunId, priority: Priority) -> None:
        """Vol.II Cap.10, secao 10.3.3. Pressuposto (garantido pelo chamador —
        Workflow Engine, Cap.9): `step` so entra aqui quando todas as suas
        dependencias ja estao `success`/`recovered` (AT-10.2)."""
        if workflow_run_id in self._cancelados:
            return
        self._fila.append(
            _EntradaFila(
                step=step,
                workflow_run_id=workflow_run_id,
                prioridade_base=priority,
                enfileirado_em=self._relogio(),
            )
        )

    def cancel(self, workflow_run_id: WorkflowRunId) -> None:
        """Vol.II Cap.10, secao 10.3.3 — cancelamento cooperativo (ver
        Workflow Engine, Cap.9, secao 9.3): remove da fila e impede novos
        enfileiramentos para este `workflow_run_id`."""
        self._cancelados.add(workflow_run_id)
        self._fila = [e for e in self._fila if e.workflow_run_id != workflow_run_id]

    def get_queue_depth(self) -> int:
        """Vol.II Cap.10, secao 10.3.3 — observabilidade de saturacao (secao
        10.5: fila crescendo continuamente deve ser alarmavel externamente,
        nunca descartar trabalho em silencio)."""
        return len(self._fila)

    def despachar_proximos(self, limite: int | None = None) -> list[PlanStep]:
        """Seleciona ate `capacidade` (ou `limite`) steps por prioridade
        efetiva (aging incluido), maior primeiro; empates resolvidos por
        ordem de chegada (FIFO) para nao introduzir escolha arbitraria."""
        agora_ = self._relogio()
        capacidade = limite if limite is not None else self._capacidade
        ordenados = sorted(
            enumerate(self._fila),
            key=lambda par: (
                -par[1].prioridade_efetiva(agora_, self._incremento_aging),
                par[0],
            ),
        )
        indices_selecionados = {indice for indice, _ in ordenados[:capacidade]}
        selecionados = [
            entrada for indice, entrada in enumerate(self._fila) if indice in indices_selecionados
        ]
        self._fila = [
            entrada
            for indice, entrada in enumerate(self._fila)
            if indice not in indices_selecionados
        ]
        return [entrada.step for entrada in selecionados]
