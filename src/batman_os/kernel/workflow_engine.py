"""Vol. II, Cap. 9 — Workflow Engine.

Executa um `ExecutionPlan` já com todas as decisões resolvidas: ordem de
passos, checkpoints, estratégias de recuperação e cancelamento cooperativo.
Maior superfície de risco operacional do Kernel — é aqui que Capabilities são
de fato invocadas.

Fonte da verdade: docs/spec/02-kernel/05-workflow-engine.md
"""

from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from batman_os.foundation.types import (
    MissionId,
    PlanId,
    RecoveryStrategy,
    StepId,
    TenantId,
    Timestamp,
    TipoRecoveryStrategy,
    WorkflowRunId,
    agora,
    novo_uuid7,
)
from batman_os.kernel.planning_engine import ExecutionPlan, PlanStep

EstadoWorkflowRun = Literal["running", "paused", "completed", "failed", "cancelled"]
StatusStepResult = Literal["success", "failed", "recovered"]


class ErrorEvidence(BaseModel):
    """Evidencia minima de falha — a especificacao referencia `ErrorEvidence`
    em varios capitulos sem detalhar sua estrutura completa; modelo mínimo
    (Evidence First: sempre uma mensagem + detalhes estruturados)."""

    mensagem: str
    detalhes: dict[str, Any] = Field(default_factory=dict)


class StepResult(BaseModel):
    """Vol.II Cap.9, secao 9.2."""

    step_id: StepId
    status: StatusStepResult
    output: Any | None = None
    erro: ErrorEvidence | None = None
    tentativa: int = 1
    iniciado_em: Timestamp = Field(default_factory=agora)
    finalizado_em: Timestamp = Field(default_factory=agora)


class Checkpoint(BaseModel):
    """Vol.II Cap.9, secao 9.2 — ponto seguro de retomada, criado sempre após
    um passo bem-sucedido (secao 9.3, regra 3)."""

    apos_step_id: StepId
    snapshot_estado: Any = None
    criado_em: Timestamp = Field(default_factory=agora)


class WorkflowRun(BaseModel):
    """Vol.II Cap.9, secao 9.2.

    `tenant_id` obrigatorio desde Vol.III Cap.14 (ADR-0005)."""

    id: WorkflowRunId = Field(default_factory=lambda: WorkflowRunId(novo_uuid7()))
    mission_id: MissionId
    tenant_id: TenantId
    plan_id: PlanId
    current_step_id: StepId | None = None
    completed_steps: list[StepResult] = Field(default_factory=list)
    checkpoints: list[Checkpoint] = Field(default_factory=list)
    estado: EstadoWorkflowRun = "running"


class ResultadoInvocacao(BaseModel):
    """Resultado bruto de invocar a Capability por trás de um `PlanStep` —
    quem produz isso de verdade é o Execution Engine (Cap.12, tarefa futura
    desta construção); aqui apenas o contrato que o Workflow Engine consome."""

    sucesso: bool
    output: Any | None = None
    erro: ErrorEvidence | None = None


class InvocadorDeStep(Protocol):
    """Vol.II Cap.9 — quem efetivamente invoca uma Capability por trás de um
    `PlanStep`. Definido como Protocol para não criar dependência do Execution
    Engine (Cap.12) antes dele existir."""

    def invocar(self, step: PlanStep) -> ResultadoInvocacao: ...


class WorkflowRunDesconhecido(Exception):
    """Levantada ao referenciar um `WorkflowRunId` inexistente."""


class WorkflowEngine:
    """Vol.II Cap.9. Não decide QUANDO nem COM QUE PARALELISMO um passo é
    despachado — isso é do Scheduler (Cap.10, próxima tarefa desta
    construção); aqui apenas a execução determinística de um passo já
    despachado, com checkpoint e recuperação."""

    def __init__(self, invocador: InvocadorDeStep) -> None:
        self._invocador = invocador
        self._runs: dict[WorkflowRunId, WorkflowRun] = {}
        self._steps_do_plano: dict[WorkflowRunId, list[PlanStep]] = {}
        self._tentativas: dict[tuple[WorkflowRunId, StepId], int] = {}

    def iniciar(self, mission_id: MissionId, plano: ExecutionPlan) -> WorkflowRun:
        """`tenant_id` do `WorkflowRun` é sempre derivado do `ExecutionPlan`
        (nunca um parâmetro redundante que poderia divergir) — consistente
        com a propagação estrutural exigida pela ADR-0005 (Vol.III Cap.14)."""
        run = WorkflowRun(mission_id=mission_id, tenant_id=plano.tenant_id, plan_id=plano.id)
        self._runs[run.id] = run
        self._steps_do_plano[run.id] = list(plano.steps)
        return run

    def get_run(self, run_id: WorkflowRunId) -> WorkflowRun:
        if run_id not in self._runs:
            raise WorkflowRunDesconhecido(str(run_id))
        return self._runs[run_id]

    def passos_prontos(self, run_id: WorkflowRunId) -> list[PlanStep]:
        """Vol.II Cap.9, secao 9.3, regra 1 — passos cujas dependencias
        (`depende_de`) estao TODAS marcadas `success`/`recovered` e que ainda
        nao foram processados. Consumido pelo Scheduler (Cap.10) para decidir
        o que despachar; a ordem retornada nao implica ordem de despacho."""
        run = self.get_run(run_id)
        steps = self._steps_do_plano[run_id]
        concluidos_ok = {
            r.step_id for r in run.completed_steps if r.status in ("success", "recovered")
        }
        ja_processados = {r.step_id for r in run.completed_steps}
        return [
            s
            for s in steps
            if s.id not in ja_processados and all(d in concluidos_ok for d in s.depende_de)
        ]

    def executar_passo(self, run_id: WorkflowRunId, step: PlanStep) -> WorkflowRun:
        """Vol.II Cap.9, secao 9.4 — executa um passo com recuperacao
        (AT-9.1: nunca reexecuta um `StepResult` ja marcado `success`)."""
        run = self.get_run(run_id)
        ja_processado = {r.step_id for r in run.completed_steps}
        if step.id in ja_processado:
            return run

        run.current_step_id = step.id
        resultado = self._invocar_com_recuperacao(run_id, step)
        run.completed_steps.append(resultado)
        run.current_step_id = None

        if resultado.status in ("success", "recovered"):
            run.checkpoints.append(Checkpoint(apos_step_id=step.id))
            steps = self._steps_do_plano[run_id]
            todos_processados = {r.step_id for r in run.completed_steps} == {s.id for s in steps}
            if todos_processados:
                run.estado = "completed"
        else:
            # AT-9.2: falha de passo critico sem recuperacao (ou recuperacao
            # esgotada) resulta em WorkflowRun.state = failed de forma
            # deterministica, nunca em estado indefinido.
            run.estado = "failed"

        return run

    def cancelar(self, run_id: WorkflowRunId) -> WorkflowRun:
        """Vol.II Cap.9, secao 9.3, regra 4 — cancelamento cooperativo: nesta
        implementacao de referencia (sem passo em voo assincrono real), o
        cancelamento e imediato e so afeta runs ainda `running`."""
        run = self.get_run(run_id)
        if run.estado == "running":
            run.estado = "cancelled"
        return run

    def _invocar_com_recuperacao(self, run_id: WorkflowRunId, step: PlanStep) -> StepResult:
        chave = (run_id, step.id)
        tentativa = self._tentativas.get(chave, 0) + 1
        self._tentativas[chave] = tentativa

        resultado = self._invocador.invocar(step)
        if resultado.sucesso:
            return StepResult(
                step_id=step.id, status="success", output=resultado.output, tentativa=tentativa
            )

        estrategia = step.recovery_strategy
        if estrategia is None:
            return StepResult(
                step_id=step.id, status="failed", erro=resultado.erro, tentativa=tentativa
            )

        return self._aplicar_recuperacao(run_id, step, estrategia, resultado, tentativa)

    def _aplicar_recuperacao(
        self,
        run_id: WorkflowRunId,
        step: PlanStep,
        estrategia: RecoveryStrategy,
        resultado_falho: ResultadoInvocacao,
        tentativa: int,
    ) -> StepResult:
        """Vol.II Cap.9, secao 9.5."""
        if estrategia.tipo == TipoRecoveryStrategy.RETRY:
            limite = estrategia.max_tentativas or 1
            if tentativa < limite:
                return self._invocar_com_recuperacao(run_id, step)
            return StepResult(
                step_id=step.id, status="failed", erro=resultado_falho.erro, tentativa=tentativa
            )

        if estrategia.tipo == TipoRecoveryStrategy.SKIP_IF_OPTIONAL:
            return StepResult(
                step_id=step.id, status="recovered", erro=resultado_falho.erro, tentativa=tentativa
            )

        if estrategia.tipo == TipoRecoveryStrategy.COMPENSATE:
            steps = self._steps_do_plano[run_id]
            passo_compensacao = next(
                (s for s in steps if s.id == estrategia.compensation_step_id), None
            )
            if passo_compensacao is not None:
                resultado_comp = self._invocador.invocar(passo_compensacao)
                if resultado_comp.sucesso:
                    return StepResult(
                        step_id=step.id,
                        status="recovered",
                        erro=resultado_falho.erro,
                        tentativa=tentativa,
                    )
            return StepResult(
                step_id=step.id, status="failed", erro=resultado_falho.erro, tentativa=tentativa
            )

        # TipoRecoveryStrategy.ESCALATE (secao 9.5, nota de design): reabre um
        # DecisionPoint em vez de "adivinhar" um novo curso de acao. O
        # Workflow Engine nao decide sozinho — apenas sinaliza falha aqui;
        # cabe a camada de orquestracao do Kernel (Cap.5) delegar de volta ao
        # Decision Engine (Cap.8), fora do escopo deste modulo.
        return StepResult(
            step_id=step.id, status="failed", erro=resultado_falho.erro, tentativa=tentativa
        )
