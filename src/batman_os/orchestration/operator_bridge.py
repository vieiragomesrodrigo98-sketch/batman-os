"""Adaptador `Operator` (Vol.IV Cap.15) -> `OperadorExecutavel` (Vol.III Cap.12).

São dois Protocols de "executar" diferentes por design — o Execution Engine
(Cap.12) foi escrito antes do Operator (Cap.15) existir, e nunca ganhou o
parâmetro `contexto` que `Operator.execute()` exige:

- `capabilities.operator.ExecutorDeOperador.executar(capability_id, entrada,
  contexto)` — 3 argumentos, consumido por `Operator.execute()`.
- `runtime.execution_engine.OperadorExecutavel.executar(capability_id,
  entrada)` — 2 argumentos, sem contexto, consumido por
  `ExecutionEngine.invoke()`.

Este módulo constrói a ponte: o `ExecutionContext` é montado pelo chamador
(`orchestration.step_invoker`) e injetado via `definir_contexto()` antes de
cada invocação — não é thread-safe para despacho concorrente (aceitável
neste lote: não há Scheduler real, Vol.II Cap.10, orquestrando múltiplos
steps em paralelo ainda).
"""

from __future__ import annotations

from typing import Any

from batman_os.capabilities.operator import ExecutionContext, HealthStatus, Operator
from batman_os.foundation.types import CapabilityId


class ContextoNaoDefinido(Exception):
    """Levantada se `executar()` for chamado antes de `definir_contexto()` —
    nunca deve acontecer no fluxo normal (`InvocadorDeStepPadrao` sempre
    define o contexto antes de invocar), mas falhar explicitamente aqui é
    preferível a um `None` silencioso propagando para o `Operator`."""


class OperadorExecutavelAdapter:
    """Satisfaz `runtime.execution_engine.OperadorExecutavel`."""

    def __init__(self, operator: Operator) -> None:
        self._operator = operator
        self._contexto_atual: ExecutionContext | None = None

    def definir_contexto(self, contexto: ExecutionContext) -> None:
        self._contexto_atual = contexto

    def executar(self, capability_id: CapabilityId, entrada: Any) -> Any:
        if self._contexto_atual is None:
            raise ContextoNaoDefinido("definir_contexto() precisa ser chamado antes de executar()")
        return self._operator.execute(capability_id, entrada, self._contexto_atual)

    def health_check(self) -> HealthStatus:
        return self._operator.health_check()
