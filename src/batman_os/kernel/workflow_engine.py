"""Vol. II, Cap. 9 — Workflow Engine.

Executa um `ExecutionPlan` já com todas as decisões resolvidas: ordem de
passos, checkpoints, estratégias de recuperação e cancelamento cooperativo.
Maior superfície de risco operacional do Kernel — é aqui que Capabilities são
de fato invocadas.

Fonte da verdade: docs/spec/02-kernel/05-workflow-engine.md
"""

from __future__ import annotations

import threading
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
from batman_os.kernel.event_bus import EmissorKernel, EventBus, KernelEvent
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

    def __init__(self, invocador: InvocadorDeStep, event_bus: EventBus | None = None) -> None:
        """`event_bus` (Fase 2 do roadmap de plataforma, `.claude/plans/
        peaceful-wondering-hearth.md`, Estagio 2.1) — opcional, default
        `None` preserva 100% dos chamadores existentes. Quando fornecido,
        publica `WorkflowRunIniciado`/`StepCompleted`/`WorkflowRunCancelado`
        para permitir hidratacao em cache-miss; sem ele, comportamento
        identico ao anterior (so estado em memoria)."""
        self._invocador = invocador
        self._event_bus = event_bus
        self._runs: dict[WorkflowRunId, WorkflowRun] = {}
        self._steps_do_plano: dict[WorkflowRunId, list[PlanStep]] = {}
        self._tentativas: dict[tuple[WorkflowRunId, StepId], int] = {}
        # Fase 2 Estagio 2.4 — um lock por WorkflowRun guarda so a
        # contabilidade (completed_steps/checkpoints/estado), nunca a
        # invocacao em si (`_invocar_com_recuperacao` roda FORA do lock, de
        # proposito: e o trabalho lento/IO-bound que o dispatcher precisa
        # rodar de verdade em paralelo — Estagio 2.4). `_lock_dos_locks`
        # protege so a criacao lazy de um lock por run_id.
        self._locks_por_run: dict[WorkflowRunId, threading.Lock] = {}
        self._lock_dos_locks = threading.Lock()

    def _lock_do_run(self, run_id: WorkflowRunId) -> threading.Lock:
        with self._lock_dos_locks:
            if run_id not in self._locks_por_run:
                self._locks_por_run[run_id] = threading.Lock()
            return self._locks_por_run[run_id]

    def iniciar(self, mission_id: MissionId, plano: ExecutionPlan) -> WorkflowRun:
        """`tenant_id` do `WorkflowRun` é sempre derivado do `ExecutionPlan`
        (nunca um parâmetro redundante que poderia divergir) — consistente
        com a propagação estrutural exigida pela ADR-0005 (Vol.III Cap.14)."""
        run = WorkflowRun(mission_id=mission_id, tenant_id=plano.tenant_id, plan_id=plano.id)
        self._runs[run.id] = run
        self._steps_do_plano[run.id] = list(plano.steps)
        self._publicar(run, "WorkflowRunIniciado", {"plan_id": str(plano.id)})
        return run

    def repovoar_plano(self, run_id: WorkflowRunId, plano: ExecutionPlan) -> None:
        """Fase 2 Estagio 2.5 — fecha a lacuna documentada em `_hidratar_de`:
        um `WorkflowRun` hidratado via replay (Estagio 2.1) nao reconstroi
        `_steps_do_plano` sozinho (precisa do `ExecutionPlan` completo,
        obtido via `planning_engine.hidratar_plano()`, Estagio 2.2). Quem
        retoma uma Missao apos um restart chama isto antes de
        `passos_prontos()`/`executar_passo()`."""
        self._steps_do_plano[run_id] = list(plano.steps)

    def get_run(self, run_id: WorkflowRunId, mission_id: MissionId | None = None) -> WorkflowRun:
        """`mission_id` (Estagio 2.1) — usado SOMENTE em cache-miss, para
        localizar a historia da Missao no Event Bus (`replay` e indexado por
        `mission_id`, nao por `run_id`). Chamadores que so tem o `run_id` de
        um `WorkflowRun` ja em memoria continuam funcionando sem passa-lo."""
        if run_id not in self._runs:
            hidratado = self._hidratar_de(run_id, mission_id) if mission_id is not None else None
            if hidratado is None:
                raise WorkflowRunDesconhecido(str(run_id))
            self._runs[run_id] = hidratado
            return hidratado
        return self._runs[run_id]

    def _hidratar_de(self, run_id: WorkflowRunId, mission_id: MissionId) -> WorkflowRun | None:
        """Reconstrucao via replay do Event Bus, so em cache-miss. Nota de
        escopo (Estagio 2.1): reconstroi `completed_steps`/`checkpoints`/
        `estado`, mas NAO `_steps_do_plano` — isso exige o `ExecutionPlan`
        completo, persistido no Estagio 2.2. Um `WorkflowRun` hidratado aqui
        e consultavel (`get_run`), mas `passos_prontos`/`executar_passo`
        exigem que `_steps_do_plano` seja repovoado externamente primeiro."""
        if self._event_bus is None:
            return None
        historia = [
            e for e in self._event_bus.replay(mission_id) if e.payload.get("run_id") == str(run_id)
        ]
        iniciado = next((e for e in historia if e.tipo == "WorkflowRunIniciado"), None)
        if iniciado is None:
            return None

        run = WorkflowRun(
            id=run_id,
            mission_id=mission_id,
            tenant_id=iniciado.tenant_id,
            plan_id=PlanId(iniciado.payload["plan_id"]),
        )
        for evento in historia:
            if evento.tipo == "StepCompleted":
                run.completed_steps.append(StepResult.model_validate(evento.payload["step_result"]))
                if "checkpoint" in evento.payload:
                    run.checkpoints.append(Checkpoint.model_validate(evento.payload["checkpoint"]))
            run.estado = evento.payload["estado"]
        return run

    def _publicar(
        self, run: WorkflowRun, tipo_evento: str, payload_extra: dict[str, Any] | None = None
    ) -> None:
        if self._event_bus is None:
            return
        self._event_bus.publish(
            KernelEvent(
                mission_id=run.mission_id,
                tenant_id=run.tenant_id,
                tipo=tipo_evento,
                emitido_por=EmissorKernel.WORKFLOW_ENGINE,
                payload={"run_id": str(run.id), "estado": run.estado, **(payload_extra or {})},
            )
        )

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
        (AT-9.1: nunca reexecuta um `StepResult` ja marcado `success`).

        Fase 2 Estagio 2.4 — seguro para chamada concorrente por MULTIPLAS
        threads sobre o MESMO `run_id` (passos independentes despachados
        juntos pelo dispatcher, `runtime/dispatcher.py`). `_invocar_com_
        recuperacao` roda FORA do lock (e o trabalho lento que precisa
        rodar de verdade em paralelo); so a contabilidade (completed_steps/
        checkpoints/estado) e atomica via `_lock_do_run`. `current_step_id`
        é best-effort sob concorrência — com múltiplos passos em voo ao
        mesmo tempo, reflete apenas o último a iniciar, não um conjunto
        (o modelo `WorkflowRun` tem um único campo escalar, Vol.II Cap.9);
        informativo, nunca usado para decisão de controle."""
        run = self.get_run(run_id)
        lock = self._lock_do_run(run_id)

        with lock:
            ja_processado = {r.step_id for r in run.completed_steps}
            if step.id in ja_processado:
                return run
            run.current_step_id = step.id

        resultado = self._invocar_com_recuperacao(run_id, step)

        with lock:
            run.completed_steps.append(resultado)
            run.current_step_id = None

            checkpoint: Checkpoint | None = None
            if resultado.status in ("success", "recovered"):
                checkpoint = Checkpoint(apos_step_id=step.id)
                run.checkpoints.append(checkpoint)

            steps = self._steps_do_plano[run_id]
            todos_ids = {s.id for s in steps}
            status_por_step = {r.step_id: r.status for r in run.completed_steps}
            algum_falhou = any(status == "failed" for status in status_por_step.values())
            todos_processados = set(status_por_step) == todos_ids

            if algum_falhou:
                # AT-9.2: falha de qualquer passo do plano — mesmo um passo
                # IRMAO, concluido em paralelo com sucesso — resulta em
                # WorkflowRun.state = failed, nunca sobrescrito de volta a
                # completed por uma checagem tardia de outro passo bem
                # sucedido (a race que a checagem ingenua por igualdade de
                # conjuntos, sem olhar status, permitia sob dispatch
                # concorrente real).
                run.estado = "failed"
            elif todos_processados:
                run.estado = "completed"

            payload_extra: dict[str, Any] = {"step_result": resultado.model_dump(mode="json")}
            if checkpoint is not None:
                payload_extra["checkpoint"] = checkpoint.model_dump(mode="json")
            self._publicar(run, "StepCompleted", payload_extra)

        return run

    def cancelar(self, run_id: WorkflowRunId) -> WorkflowRun:
        """Vol.II Cap.9, secao 9.3, regra 4 — cancelamento cooperativo: nesta
        implementacao de referencia (sem passo em voo assincrono real), o
        cancelamento e imediato e so afeta runs ainda `running`."""
        run = self.get_run(run_id)
        if run.estado == "running":
            run.estado = "cancelled"
            self._publicar(run, "WorkflowRunCancelado")
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
