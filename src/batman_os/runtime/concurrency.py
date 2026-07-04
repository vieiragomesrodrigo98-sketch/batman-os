"""Vol. III, Cap. 14 — Concorrência e Isolamento de Missões.

Detalha, em profundidade, como múltiplas Missões — potencialmente de tenants
diferentes — coexistem na mesma instância do Batman OS sem interferência
indevida entre si. `tenant_id` (ADR-0005) já foi propagado estruturalmente
por Mission (Cap.6), ExecutionPlan (Cap.7), WorkflowRun (Cap.9),
OperationalRecord (Cap.13) e KernelEvent (Cap.10) nesta construção; este
módulo formaliza a extensão de fairness do Scheduler (Cap.10) por tenant —
as demais dimensões de isolamento (recurso: bulkhead do Execution Engine,
Cap.12; dados: filtro por tenant da Operational Memory, Cap.13; falha:
isolamento por `WorkflowRunId` já estrutural no Workflow Engine, Cap.9) já
foram cobertas nos capítulos correspondentes.

Fonte da verdade: docs/spec/03-runtime/04-concurrency-isolation.md
"""

from __future__ import annotations

from batman_os.foundation.types import TenantId, WorkflowRunId
from batman_os.kernel.planning_engine import PlanStep
from batman_os.kernel.scheduler import Priority, Scheduler


class TenantQuotas:
    """Vol.III Cap.14, secao 14.5 — pesos configuráveis por tenant, usados
    pelo weighted round-robin. Configuração explícita e revisável (Governance
    Engine, Volume VII, fora de escopo), nunca heurística implícita."""

    def __init__(
        self, pesos: dict[TenantId, float] | None = None, peso_padrao: float = 1.0
    ) -> None:
        self._pesos = dict(pesos or {})
        self._peso_padrao = peso_padrao

    def peso(self, tenant_id: TenantId) -> float:
        return self._pesos.get(tenant_id, self._peso_padrao)


class SchedulerComFairnessPorTenant:
    """Vol.III Cap.14, secao 14.5 — estende o Scheduler (Vol.II Cap.10) com
    fairness explícita por tenant: cada tenant tem sua própria fila interna
    (um `Scheduler` dedicado, com prioridade+aging já implementados no
    Cap.10), e a escolha de QUAL tenant despachar a seguir usa weighted
    round-robin (secao 14.5) — nunca "quem chegou primeiro" (secao 14.5)."""

    def __init__(self, quotas: TenantQuotas, capacidade_por_despacho: int = 1) -> None:
        self._quotas = quotas
        self._capacidade_por_despacho = capacidade_por_despacho
        self._filas_por_tenant: dict[TenantId, Scheduler] = {}
        self._credito_round_robin: dict[TenantId, float] = {}

    def enqueue(
        self,
        tenant_id: TenantId,
        step: PlanStep,
        workflow_run_id: WorkflowRunId,
        priority: Priority,
    ) -> None:
        self._fila_do_tenant(tenant_id).enqueue(step, workflow_run_id, priority)

    def get_queue_depth(self, tenant_id: TenantId) -> int:
        return self._fila_do_tenant(tenant_id).get_queue_depth()

    def despachar_proximo(self) -> tuple[TenantId, list[PlanStep]] | None:
        """Vol.III Cap.14, secao 14.5 (`selectNextStep`) — escolhe o tenant
        elegível (fila não vazia) via weighted round-robin; dentro da fila do
        tenant escolhido, despacha pela prioridade efetiva já implementada no
        Scheduler (Cap.10, `despachar_proximos`)."""
        elegiveis = [t for t, fila in self._filas_por_tenant.items() if fila.get_queue_depth() > 0]
        if not elegiveis:
            return None
        tenant_escolhido = self._weighted_round_robin(elegiveis)
        passos = self._filas_por_tenant[tenant_escolhido].despachar_proximos()
        return tenant_escolhido, passos

    def _fila_do_tenant(self, tenant_id: TenantId) -> Scheduler:
        if tenant_id not in self._filas_por_tenant:
            self._filas_por_tenant[tenant_id] = Scheduler(
                capacidade_worker_pool=self._capacidade_por_despacho
            )
        return self._filas_por_tenant[tenant_id]

    def _weighted_round_robin(self, elegiveis: list[TenantId]) -> TenantId:
        """Smooth Weighted Round-Robin (algoritmo clássico de balanceamento,
        popularizado pelo Nginx): cada tenant acumula crédito proporcional ao
        seu peso a cada rodada; o de maior crédito é escolhido e tem seu
        crédito decrementado pela soma total dos pesos elegíveis. Garante
        proporcionalidade de longo prazo sem sequências longas do mesmo
        tenant (AT-14.2) — a especificação nomeia o algoritmo mas não
        detalha a implementação exata."""
        for tenant_id in elegiveis:
            self._credito_round_robin.setdefault(tenant_id, 0.0)
            self._credito_round_robin[tenant_id] += self._quotas.peso(tenant_id)

        escolhido = max(elegiveis, key=lambda t: self._credito_round_robin[t])
        soma_pesos = sum(self._quotas.peso(t) for t in elegiveis)
        self._credito_round_robin[escolhido] -= soma_pesos
        return escolhido
