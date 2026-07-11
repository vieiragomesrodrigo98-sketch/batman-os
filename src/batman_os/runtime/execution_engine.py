"""Vol. III, Cap. 12 — Execution Engine.

Camada que efetivamente invoca uma Capability resolvida contra um Operador
concreto — o ponto exato em que o Batman OS toca o mundo real. Fronteira
entre o Kernel determinístico e o mundo externo, necessariamente não
determinístico em latência e disponibilidade (ainda que determinístico em
contrato de dados).

Fonte da verdade: docs/spec/03-runtime/02-execution-engine.md
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturoTimeoutError
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from batman_os.foundation.types import CapabilityId, OperatorId, OperatorRef
from batman_os.kernel.workflow_engine import ErrorEvidence
from batman_os.runtime.capability_engine import CapabilityDefinition

StatusExecutionResult = Literal["success", "failure", "timeout"]


class ResourceUsage(BaseModel):
    """Vol.III Cap.12, secao 12.2 — insumo de billing/observabilidade."""

    cpu_ms: float = 0.0
    memoria_mb: float = 0.0
    chamadas_rede: int = 0


class ExecutionResult(BaseModel):
    """Vol.III Cap.12, secao 12.2."""

    status: StatusExecutionResult
    output: Any | None = None
    erro: ErrorEvidence | None = None
    duration_ms: float
    resource_usage: ResourceUsage = Field(default_factory=ResourceUsage)


class OperadorExecutavel(Protocol):
    """Vol.III Cap.12 — quem efetivamente executa uma Capability. Papel
    análogo a `Operator.execute()` (Vol.IV Cap.15, tarefa futura desta
    construção); aqui apenas o contrato mínimo que o Execution Engine
    consome, para não depender do módulo de Operador antes dele existir."""

    def executar(self, capability_id: CapabilityId, entrada: Any) -> Any: ...


class LimitadorDeRecurso(Protocol):
    """Vol.III Cap.12, secao 12.4 — bulkhead: orçamento de recurso isolado
    por Operador."""

    def reservar(self, operator_ref: OperatorRef) -> bool: ...

    def liberar(self, operator_ref: OperatorRef) -> None: ...


class ValidadorSchema(Protocol):
    """Valida a saída de uma Capability contra seu `outputSchema` (Vol.III
    Cap.11). Implementação real usaria um validador JSON Schema completo
    (fora das dependências desta construção); aqui o contrato mínimo."""

    def validar(self, output: Any, output_schema: dict[str, Any]) -> bool: ...


class ValidadorContratoNaoDeterministico(Protocol):
    """Vol.III Cap.12, secao 12.5 — validação ADICIONAL, exigida apenas para
    Capabilities `deterministic: false` (LLM Gateway como Operador especial),
    antes mesmo da validação padrão de `outputSchema`. Papel análogo ao
    `ValidadorContrato` do Decision Engine (Vol.II Cap.8), mas aplicado no
    nível de invocação de Capability — tipos diferentes, mesma doutrina de
    nunca confiar cegamente em saída não determinística."""

    def validar(self, capability: CapabilityDefinition, output: Any) -> bool: ...


class LimitadorPermissivo:
    """Bulkhead no-op — usado quando nenhum `LimitadorDeRecurso` real é
    fornecido. Nunca deve ser o padrão em produção; existe para permitir
    testar o Execution Engine isoladamente sem exigir um limitador real."""

    def reservar(self, operator_ref: OperatorRef) -> bool:
        del operator_ref
        return True

    def liberar(self, operator_ref: OperatorRef) -> None:
        del operator_ref


class LimitadorDeRecursoPorOperador:
    """Vol.III Cap.12, secao 12.4 — implementação de referência do bulkhead:
    limite de chamadas concorrentes por Operador, independente entre
    Operadores distintos (AT-12.3: um Operador instável nunca esgota o
    orçamento de outro)."""

    def __init__(self, limite_concorrente_por_operador: int = 1) -> None:
        self._limite = limite_concorrente_por_operador
        self._em_uso: dict[OperatorId, int] = {}
        self._lock = threading.Lock()

    def reservar(self, operator_ref: OperatorRef) -> bool:
        with self._lock:
            atual = self._em_uso.get(operator_ref.operator_id, 0)
            if atual >= self._limite:
                return False
            self._em_uso[operator_ref.operator_id] = atual + 1
            return True

    def liberar(self, operator_ref: OperatorRef) -> None:
        with self._lock:
            atual = self._em_uso.get(operator_ref.operator_id, 0)
            self._em_uso[operator_ref.operator_id] = max(0, atual - 1)


class ExecutionEngine:
    """Vol.III Cap.12."""

    def __init__(
        self,
        validador_schema: ValidadorSchema,
        validador_contrato_nao_deterministico: ValidadorContratoNaoDeterministico,
        limitador: LimitadorDeRecurso | None = None,
        max_workers: int = 8,
    ) -> None:
        self._validador_schema = validador_schema
        self._validador_contrato_nao_deterministico = validador_contrato_nao_deterministico
        self._limitador = limitador or LimitadorPermissivo()
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        # Fase 2 Estagio 2.3 — pool SEPARADO do `_executor` acima. `submit()`
        # enfileira aqui a espera bloqueante (bulkhead + result(timeout=...) +
        # validacao); `_executor` continua exclusivo para `operador.executar`.
        # Enfileirar as duas coisas no MESMO pool arrisca deadlock por
        # esgotamento de workers assim que o Scheduler (Estagio 2.4) despachar
        # mais chamadas concorrentes que `max_workers`: cada worker do
        # "supervisor" ficaria bloqueado esperando um worker de `_executor`
        # que nunca sobraria.
        self._supervisor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="execution-engine-supervisor"
        )

    def fechar(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
        self._supervisor.shutdown(wait=False, cancel_futures=True)

    def submit(
        self,
        capability: CapabilityDefinition,
        operador: OperadorExecutavel,
        operator_ref: OperatorRef,
        entrada: Any,
        timeout_segundos: float,
    ) -> Future[ExecutionResult]:
        """Fase 2 Estagio 2.3 — versao nao-bloqueante de `invoke()`: retorna
        um `Future` imediatamente, sem esperar a Capability concluir.
        `invoke()` e um wrapper sincrono sobre este metodo — comportamento
        identico ao anterior para todo chamador existente."""
        return self._supervisor.submit(
            self._invocar_bloqueante, capability, operador, operator_ref, entrada, timeout_segundos
        )

    def invoke(
        self,
        capability: CapabilityDefinition,
        operador: OperadorExecutavel,
        operator_ref: OperatorRef,
        entrada: Any,
        timeout_segundos: float,
    ) -> ExecutionResult:
        """Vol.III Cap.12, secao 12.3."""
        return self.submit(capability, operador, operator_ref, entrada, timeout_segundos).result()

    def _invocar_bloqueante(
        self,
        capability: CapabilityDefinition,
        operador: OperadorExecutavel,
        operator_ref: OperatorRef,
        entrada: Any,
        timeout_segundos: float,
    ) -> ExecutionResult:
        inicio = time.monotonic()

        if not self._limitador.reservar(operator_ref):
            return ExecutionResult(
                status="failure",
                erro=ErrorEvidence(
                    mensagem="orcamento de recurso indisponivel para este Operador (bulkhead)"
                ),
                duration_ms=(time.monotonic() - inicio) * 1000,
            )

        try:
            futuro: Future[Any] = self._executor.submit(operador.executar, capability.id, entrada)
            try:
                output = futuro.result(timeout=timeout_segundos)
            except FuturoTimeoutError:
                futuro.cancel()
                return ExecutionResult(
                    status="timeout", duration_ms=(time.monotonic() - inicio) * 1000
                )
            except Exception as exc:  # noqa: BLE001 - falha do Operador vira ExecutionResult, nunca propaga
                return ExecutionResult(
                    status="failure",
                    erro=ErrorEvidence(mensagem=str(exc)),
                    duration_ms=(time.monotonic() - inicio) * 1000,
                )
        finally:
            self._limitador.liberar(operator_ref)

        duracao_ms = (time.monotonic() - inicio) * 1000

        if not capability.deterministic and not self._validador_contrato_nao_deterministico.validar(
            capability, output
        ):
            return ExecutionResult(
                status="failure",
                erro=ErrorEvidence(
                    mensagem=(
                        "saida de Capability nao-deterministica reprovada na validacao de contrato"
                    )
                ),
                duration_ms=duracao_ms,
            )

        if not self._validador_schema.validar(output, capability.output_schema):
            return ExecutionResult(
                status="failure",
                erro=ErrorEvidence(mensagem="saida viola outputSchema da Capability"),
                duration_ms=duracao_ms,
            )

        return ExecutionResult(status="success", output=output, duration_ms=duracao_ms)
