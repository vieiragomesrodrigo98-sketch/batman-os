"""Roteador `capability_id -> handler` (Vol.IV Cap.15).

`runtime.capability_engine.CapabilityRegistry` só guarda `CapabilityDefinition`
(schema/metadados) — o `handler` de verdade mora em `CapabilityImplementation`
(Vol.IV Cap.16), que não tem registro central algum na especificação. Esta
classe preenche essa lacuna: satisfaz `capabilities.operator.ExecutorDeOperador`
(o Protocol que `Operator.execute()` de fato invoca), roteando para o handler
certo por `CapabilityId`.
"""

from __future__ import annotations

from typing import Any

from batman_os.capabilities.capability_contract import CapabilityImplementation
from batman_os.capabilities.operator import ExecutionContext, HealthStatus
from batman_os.foundation.types import CapabilityId


class CapabilityNaoImplementada(Exception):
    """Levantada quando não há `CapabilityImplementation` registrada para o
    `CapabilityId` solicitado — distinto de `CapabilityNaoEncontrada`
    (`runtime/capability_engine.py`), que fala do catálogo de definições,
    não de quem de fato implementa o handler."""


class ExecutorViaImplementacoes:
    """Satisfaz `capabilities.operator.ExecutorDeOperador`. Roteia
    `capability_id -> CapabilityImplementation.handler` via um registro
    local simples — suficiente para este primeiro lote (1 Capability
    genérica); um registro central mais sofisticado (com ciclo de vida
    próprio) é trabalho futuro se o número de implementações crescer."""

    def __init__(self, implementacoes: dict[CapabilityId, CapabilityImplementation]) -> None:
        self._implementacoes = dict(implementacoes)

    def executar(
        self, capability_id: CapabilityId, entrada: Any, contexto: ExecutionContext
    ) -> Any:
        implementacao = self._implementacoes.get(capability_id)
        if implementacao is None:
            raise CapabilityNaoImplementada(str(capability_id))
        return implementacao.handler(entrada, contexto)

    def health_check(self) -> HealthStatus:
        return HealthStatus(saudavel=True)
