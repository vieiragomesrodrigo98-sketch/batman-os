"""Vol.IX Cap.34 (extensão HTTP), Fase 6, Estágio 6.2 — colaboradores
compartilhados do app FastAPI.

Mapa de custo confirmado por investigação direta antes de desenhar esta
fase (`.claude/plans/peaceful-wondering-hearth.md`, "Achado 2" da Fase
6): nenhum destes objetos guarda estado por requisição — `CapabilityRegistry`/
`Operator` (custo de recertificação pago uma vez), `EventBus` real
(thread-safe via lock+WAL, `kernel/event_bus.py`), `DecisionEngine`
(contadores já protegidos por lock desde a Fase 2), `MissionRuntime`
(delega tudo ao `EventBus`, não guarda nada por conta própria) e
`ExecutionEngine` (dois `ThreadPoolExecutor`s, fechados exatamente uma
vez no shutdown do `lifespan`, nunca por requisição)."""

from __future__ import annotations

from dataclasses import dataclass

from batman_os.capabilities.operator import Operator
from batman_os.kernel.decision_engine import DecisionEngine
from batman_os.kernel.mission_runtime import MissionRuntime
from batman_os.runtime.capability_engine import CapabilityRegistry
from batman_os.runtime.execution_engine import ExecutionEngine


@dataclass
class ColaboradoresCompartilhados:
    registry: CapabilityRegistry
    operator: Operator
    runtime: MissionRuntime
    decision_engine: DecisionEngine
    execution_engine: ExecutionEngine
