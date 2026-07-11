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
vez no shutdown do `lifespan`, nunca por requisição).

`event_bus`/`pool_missoes`/`job_store` (Fase 7, Estágio 7.2) — `event_bus`
é a MESMA instância já usada pelo `MissionRuntime`, exposta explicitamente
aqui (`MissionRuntime._event_bus` é privado, sem getter público) para ser
repassada também ao driver (`continuar_missao_via_playbook(...,
event_bus=...)`, Estágio 7.1) e persistir o plano. `pool_missoes` é um
`ThreadPoolExecutor` NOVO e DEDICADO — nunca reaproveita `ExecutionEngine.
_executor`/`_supervisor` (dimensionados e documentados como exclusivos de
UMA invocação de Capability; achado de investigação: reentrar neles para
"Missão inteira em background" arrisca esgotar o pool sob concorrência)."""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass

from batman_os.capabilities.operator import Operator
from batman_os.foundation.types import MissionId, TenantId
from batman_os.kernel.decision_engine import DecisionEngine
from batman_os.kernel.event_bus import EventBus
from batman_os.kernel.mission_runtime import MissionRuntime
from batman_os.orchestration.playbook_driver import ResultadoMissaoPlaybook
from batman_os.orchestration.playbook_step_specs import ConstrutorDeEntrada
from batman_os.runtime.capability_engine import CapabilityRegistry
from batman_os.runtime.execution_engine import ExecutionEngine


@dataclass
class EntradaJob:
    """Fase 7, Estágio 7.2/7.3 — `resultado`/`erro` ficam `None` enquanto
    a Missão está em andamento; um dos dois é preenchido via `future.
    add_done_callback` assim que `continuar_missao_via_playbook`/
    `retomar_missao_apos_escalada` terminam. `erro` cobre o caso de uma
    exceção NÃO tratada escapar da execução em background (`PlaybookNao
    Resolvido`, `EspecificacaoDeStepAusente`, etc.) — sem isso, `future.
    result()` dentro do callback relançaria a exceção, `add_done_
    callback` a engoliria silenciosamente (comportamento documentado do
    `concurrent.futures`), e o job ficaria "em andamento" para sempre.

    `especificacoes_por_indice` (Estágio 7.3) — o `ConstrutorDeEntrada`
    por índice de step do Playbook original, guardado aqui porque é
    exatamente a peça que falta para `POST /missions/{id}/resume`
    retomar depois: sem isso, não haveria como reconstruir os steps do
    Playbook a partir só do `mission_id`/`DecisionPoint` ecoado de
    volta."""

    tenant_id: TenantId
    future: Future[ResultadoMissaoPlaybook]
    especificacoes_por_indice: dict[int, ConstrutorDeEntrada]
    resultado: ResultadoMissaoPlaybook | None = None
    erro: str | None = None


class JobStore:
    """Fase 7, Estágio 7.2 — o Kernel não persiste o `DecisionPoint`
    pendente de uma Missão escalada (achado de investigação da Fase 7),
    então a camada `api/` guarda isso por conta própria, keyed por
    `mission_id` (= `job_id`, Achado 1 da Fase 7 — não inventa um `JobId`
    paralelo, `MissionState` já é a máquina de estados). Thread-safe:
    `registrar()`/`atualizar_resultado()`/`registrar_erro()` rodam a
    partir de threads diferentes (`pool_missoes`)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entradas: dict[MissionId, EntradaJob] = {}

    def registrar(
        self,
        mission_id: MissionId,
        tenant_id: TenantId,
        future: Future[ResultadoMissaoPlaybook],
        especificacoes_por_indice: dict[int, ConstrutorDeEntrada],
    ) -> None:
        with self._lock:
            self._entradas[mission_id] = EntradaJob(
                tenant_id=tenant_id,
                future=future,
                especificacoes_por_indice=especificacoes_por_indice,
            )

    def atualizar_resultado(
        self, mission_id: MissionId, resultado: ResultadoMissaoPlaybook
    ) -> None:
        with self._lock:
            entrada = self._entradas.get(mission_id)
            if entrada is not None:
                entrada.resultado = resultado

    def registrar_erro(self, mission_id: MissionId, erro: str) -> None:
        with self._lock:
            entrada = self._entradas.get(mission_id)
            if entrada is not None:
                entrada.erro = erro

    def consultar(self, mission_id: MissionId) -> EntradaJob | None:
        with self._lock:
            return self._entradas.get(mission_id)

    def callback_de_desfecho(
        self, mission_id: MissionId
    ) -> Callable[[Future[ResultadoMissaoPlaybook]], None]:
        """Fabrica um callback pronto para `future.add_done_callback()`
        — cobre tanto o caminho feliz quanto uma exceção não tratada
        escapando da execução em background (ver docstring de
        `EntradaJob`)."""

        def _callback(future: Future[ResultadoMissaoPlaybook]) -> None:
            try:
                resultado = future.result()
            except Exception as exc:  # noqa: BLE001 - preserva a falha no job, nunca a silencia
                self.registrar_erro(mission_id, str(exc))
            else:
                self.atualizar_resultado(mission_id, resultado)

        return _callback


@dataclass
class ColaboradoresCompartilhados:
    registry: CapabilityRegistry
    operator: Operator
    runtime: MissionRuntime
    decision_engine: DecisionEngine
    execution_engine: ExecutionEngine
    event_bus: EventBus
    pool_missoes: ThreadPoolExecutor
    job_store: JobStore
