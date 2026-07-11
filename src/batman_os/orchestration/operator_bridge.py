"""Adaptador `Operator` (Vol.IV Cap.15) -> `OperadorExecutavel` (Vol.III Cap.12).

São dois Protocols de "executar" diferentes por design — o Execution Engine
(Cap.12) foi escrito antes do Operator (Cap.15) existir, e nunca ganhou o
parâmetro `contexto` que `Operator.execute()` exige:

- `capabilities.operator.ExecutorDeOperador.executar(capability_id, entrada,
  contexto)` — 3 argumentos, consumido por `Operator.execute()`.
- `runtime.execution_engine.OperadorExecutavel.executar(capability_id,
  entrada)` — 2 argumentos, sem contexto, consumido por
  `ExecutionEngine.invoke()`.

Este módulo constrói a ponte: o `ExecutionContext` é passado ao construtor,
imutável para a vida da instância (Fase 2 do roadmap de plataforma,
`.claude/plans/peaceful-wondering-hearth.md`, Estágio 2.3). Antes, o
contexto era mutado via `definir_contexto()` num adapter reusado entre
Missões — thread-unsafe assim que duas Missões passam a rodar em paralelo
(Estágio 2.4): uma poderia sobrescrever o contexto da outra entre
`definir_contexto()` e `executar()`. Quem despacha um step agora cria um
adapter novo por invocação (`orchestration.step_invoker`); o `Operator`
em si continua reutilizável (é stateless por contrato, Vol.IV Cap.15).
"""

from __future__ import annotations

from typing import Any

from batman_os.capabilities.operator import ExecutionContext, HealthStatus, Operator
from batman_os.foundation.types import CapabilityId


class OperadorExecutavelAdapter:
    """Satisfaz `runtime.execution_engine.OperadorExecutavel`."""

    def __init__(self, operator: Operator, contexto: ExecutionContext) -> None:
        self._operator = operator
        self._contexto = contexto

    def executar(self, capability_id: CapabilityId, entrada: Any) -> Any:
        return self._operator.execute(capability_id, entrada, self._contexto)

    def health_check(self) -> HealthStatus:
        return self._operator.health_check()
