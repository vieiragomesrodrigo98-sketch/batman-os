"""Entrega o payload de um `PlanStep` ao Execution Engine (Vol.II Cap.9 + Vol.III Cap.12).

`PlanStep` (`kernel/planning_engine.py`) não carrega payload de entrada — só
`capability`, `depende_de`, `decision_point_id`, `recovery_strategy` (Vol.II
Cap.7, secao 7.3). Em vez de estender um módulo com testes de aceitação
(AT-7.x) já fechados, uma tabela lateral (`StepId -> entrada`), populada pelo
chamador logo após `plan()` retornar (quando os `StepId`s já são conhecidos),
resolve isso sem tocar código governado por spec.

`InvocadorDeStepPadrao` satisfaz `kernel.workflow_engine.InvocadorDeStep` — a
peça que o `WorkflowEngine` de fato consome a cada passo.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from batman_os.capabilities.operator import ExecutionContext, Operator
from batman_os.foundation.types import MissionId, OperatorRef, StepId, TenantId, agora
from batman_os.kernel.planning_engine import PlanStep
from batman_os.kernel.workflow_engine import ResultadoInvocacao
from batman_os.orchestration.operator_bridge import OperadorExecutavelAdapter
from batman_os.runtime.capability_engine import CapabilityRegistry
from batman_os.runtime.execution_engine import ExecutionEngine


class EntradaNaoRegistrada(Exception):
    """Levantada quando `obter()` é chamado para um `StepId` sem entrada
    registrada — falha explícita em vez de propagar um payload ausente em
    silêncio para o handler da Capability."""


class TabelaDeEntradasPorStep:
    """`StepId -> entrada` — populada pelo chamador (`cli/scan_command.py`)
    logo após `plan()` retornar, quando os `StepId`s já são conhecidos."""

    def __init__(self) -> None:
        self._entradas: dict[StepId, Any] = {}

    def registrar(self, step_id: StepId, entrada: Any) -> None:
        self._entradas[step_id] = entrada

    def obter(self, step_id: StepId) -> Any:
        if step_id not in self._entradas:
            raise EntradaNaoRegistrada(str(step_id))
        return self._entradas[step_id]


class InvocadorDeStepPadrao:
    """Satisfaz `kernel.workflow_engine.InvocadorDeStep`.

    Simplificação assumida neste primeiro lote: um `WorkflowEngine`/
    invocador novo por Missão, não um único de longa duração multiplexando
    vários `WorkflowRun`s concorrentes — falta o Scheduler real (Vol.II
    Cap.10) para isso; extensão natural quando ele existir.

    Recebe o `Operator` bruto (nao um `OperadorExecutavelAdapter` ja
    construido) desde a Fase 2, Estagio 2.3 — um `OperadorExecutavelAdapter`
    novo, com contexto imutavel escopado a este passo, e construido a cada
    `invocar()`. `Operator` em si e reutilizavel entre Missoes (stateless);
    so o contexto precisa ser por-chamada."""

    def __init__(
        self,
        execution_engine: ExecutionEngine,
        operator: Operator,
        operator_ref: OperatorRef,
        capability_registry: CapabilityRegistry,
        tabela_entradas: TabelaDeEntradasPorStep,
        mission_id: MissionId,
        tenant_id: TenantId,
        timeout_segundos: float = 5.0,
    ) -> None:
        self._execution_engine = execution_engine
        self._operator = operator
        self._operator_ref = operator_ref
        self._capability_registry = capability_registry
        self._tabela_entradas = tabela_entradas
        self._mission_id = mission_id
        self._tenant_id = tenant_id
        self._timeout_segundos = timeout_segundos

    def invocar(self, step: PlanStep) -> ResultadoInvocacao:
        entrada = self._tabela_entradas.obter(step.id)
        capability = self._capability_registry.resolve(step.capability)

        contexto = ExecutionContext(
            mission_id=self._mission_id,
            tenant_id=self._tenant_id,
            step_id=step.id,
            deadline=agora() + timedelta(seconds=self._timeout_segundos),
        )
        adapter = OperadorExecutavelAdapter(self._operator, contexto)

        resultado = self._execution_engine.invoke(
            capability, adapter, self._operator_ref, entrada, self._timeout_segundos
        )
        return ResultadoInvocacao(
            sucesso=resultado.status == "success", output=resultado.output, erro=resultado.erro
        )
