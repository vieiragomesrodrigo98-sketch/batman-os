"""Vol. II Cap.6/9 + Vol. VII Cap.28 — retomada de Missões após restart do
processo + alarme de SLA de Human Review.

Fase 2 do roadmap de plataforma (`.claude/plans/peaceful-wondering-hearth.md`,
Estágio 2.5, final). Duas peças já existiam separadas, nunca conectadas:
`verificar_sla_e_alarmar()` (`governance/human_review.py`) — testada, mas
sem nenhum chamador em `src/`; e a hidratação de Mission/WorkflowRun/
ExecutionPlan (Estágios 2.1/2.2) — testada isoladamente, mas nunca usada
para de fato retomar uma execução em `AwaitingHuman`.

Este módulo vive em `orchestration/` (não em `governance/`) por decisão
deliberada: `governance/governance_engine.py` se autodocumenta com ADR-0012
— "Governance Engine sem autoridade executiva direta... este módulo NUNCA
importa de `batman_os.kernel`" — porque Governance Engine só informa/alarma,
nunca decide ou executa nada do Kernel por substituição. Retomar uma Missão
(chamar `DecisionEngine.resolver_com_resposta_humana`, `MissionRuntime.
transition`, `WorkflowEngine.executar_passo`) é exatamente a ação executiva
que a ADR proíbe dentro de `governance/`. `orchestration/` já é o pacote que
liga Kernel a execução real (`step_invoker.py`, `operator_bridge.py`) — o
lugar correto para esta peça também.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from batman_os.foundation.types import (
    DecisionOption,
    Evidence,
    MissionId,
    TenantId,
    WorkflowRunId,
)
from batman_os.governance.governance_engine import GovernanceAlert, GovernanceEngine
from batman_os.governance.human_review import HumanReviewRequest, verificar_sla_e_alarmar
from batman_os.kernel.decision_engine import DecisionEngine
from batman_os.kernel.event_bus import EventBus
from batman_os.kernel.mission_runtime import MissionEventType, MissionRuntime, MissionState
from batman_os.kernel.planning_engine import DecisionPoint, hidratar_plano
from batman_os.kernel.scheduler import Scheduler
from batman_os.kernel.workflow_engine import WorkflowEngine
from batman_os.runtime.dispatcher import RunAcompanhada, despachar_ate_terminal


@dataclass(frozen=True)
class RespostaHumanaChegada:
    """Uma decisão humana que chegou para uma Missão em `AwaitingHuman`. O
    watchdog não sabe (nem precisa saber) COMO ela chegou — API, fila,
    planilha — quem monta esta estrutura é quem traduz o canal real
    (fora de escopo desta construção, ver nota de exclusão no fim do
    módulo). `workflow_run_id` é necessário explicitamente: `Mission.
    workflow_run_id` (Vol.II Cap.6) nunca é populado neste build (achado
    de auditoria já documentado, `project_batman_os_status`), então não há
    como descobri-lo a partir só do `mission_id`."""

    mission_id: MissionId
    tenant_id: TenantId
    workflow_run_id: WorkflowRunId
    ponto: DecisionPoint
    opcao_escolhida: DecisionOption
    evidencia: list[Evidence]


@dataclass
class ResultadoCicloWatchdog:
    """Resultado de um ciclo do watchdog — as duas responsabilidades
    (alarme de SLA, retomada de Missão) são independentes; a falha de uma
    retomada nunca impede as demais nem os alarmes de SLA."""

    alertas_sla: list[GovernanceAlert] = field(default_factory=list)
    missoes_retomadas: list[MissionId] = field(default_factory=list)
    missoes_com_falha_ao_retomar: dict[MissionId, str] = field(default_factory=dict)


class MissaoNaoRetomavel(Exception):
    """Levantada quando a Missão referenciada não está em `AwaitingHuman`,
    ou não tem `ExecutionPlan` persistido (`event_bus` não foi passado a
    `plan()` na execução original, Estágio 2.2) — retomar exige as duas
    condições."""


def retomar_missao(
    resposta: RespostaHumanaChegada,
    event_bus: EventBus,
    runtime: MissionRuntime,
    workflow: WorkflowEngine,
    decision_engine: DecisionEngine,
    capacidade_execucao: int = 4,
) -> None:
    """Retoma UMA Missão em `AwaitingHuman`: hidrata Mission (Estágio 2.1),
    hidrata o `ExecutionPlan` CONCRETO (Estágio 2.2 — nunca replaneja, os
    `PlanStep.id` precisam bater com `completed_steps`/`Checkpoint` já
    gravados), aplica a decisão humana, e despacha os passos AINDA NÃO
    concluídos até a Missão terminar — passos já em `completed_steps`
    nunca são reexecutados (AT-9.1, `WorkflowEngine.executar_passo`)."""
    mission = runtime.get_mission(resposta.mission_id, resposta.tenant_id)
    if mission.estado != MissionState.AWAITING_HUMAN:
        raise MissaoNaoRetomavel(
            f"Missao {resposta.mission_id} nao esta em AwaitingHuman "
            f"(esta em '{mission.estado.value}') — nada a retomar"
        )

    plano = hidratar_plano(event_bus, resposta.mission_id)
    if plano is None:
        raise MissaoNaoRetomavel(
            f"Missao {resposta.mission_id} nao tem ExecutionPlan persistido "
            "(event_bus nao foi passado a plan() na execucao original) — "
            "retomada exige o plano concreto, nunca replanejar"
        )

    decision_engine.resolver_com_resposta_humana(
        resposta.ponto,
        resposta.mission_id,
        opcao_escolhida=resposta.opcao_escolhida,
        evidencia=resposta.evidencia,
    )
    runtime.transition(
        resposta.mission_id, MissionEventType.ESCALATION_RESOLVED, resposta.tenant_id
    )
    runtime.transition(resposta.mission_id, MissionEventType.DECISIONS_RESOLVED, resposta.tenant_id)

    workflow.get_run(
        resposta.workflow_run_id, mission_id=resposta.mission_id, tenant_id=resposta.tenant_id
    )
    workflow.repovoar_plano(resposta.workflow_run_id, plano)

    scheduler = Scheduler(capacidade_worker_pool=capacidade_execucao)
    despachar_ate_terminal(
        workflow,
        scheduler,
        [RunAcompanhada(run_id=resposta.workflow_run_id, tenant_id=resposta.tenant_id)],
        max_workers=capacidade_execucao,
    )

    estado_final = workflow.get_run(resposta.workflow_run_id).estado
    if estado_final == "completed":
        runtime.transition(
            resposta.mission_id, MissionEventType.WORKFLOW_COMPLETED, resposta.tenant_id
        )
    elif estado_final == "failed":
        runtime.transition(
            resposta.mission_id, MissionEventType.WORKFLOW_FAILED, resposta.tenant_id
        )


def executar_ciclo_watchdog(
    solicitacoes_human_review: list[HumanReviewRequest],
    governance: GovernanceEngine,
    respostas_humanas_chegadas: list[RespostaHumanaChegada],
    event_bus: EventBus,
    runtime: MissionRuntime,
    workflow: WorkflowEngine,
    decision_engine: DecisionEngine,
) -> ResultadoCicloWatchdog:
    """Um ciclo do watchdog faz duas coisas independentes, cada uma sem
    afetar a outra:

    1. Alarma toda `HumanReviewRequest` com SLA vencido —
       `verificar_sla_e_alarmar()` já existente (`governance/human_
       review.py`), aqui ganhando seu primeiro chamador real.
    2. Retoma cada Missão referenciada em `respostas_humanas_chegadas` —
       uma falha ao retomar UMA Missão nunca derruba o ciclo inteiro nem
       impede as demais de serem retomadas.

    Exclusão explícita desta construção: não há repositório persistido de
    `HumanReviewRequest`/canal real de "decisão humana chegou" neste
    código-base ainda — quem monta `solicitacoes_human_review`/
    `respostas_humanas_chegadas` e decide a cadência de chamada (cron,
    daemon) é responsabilidade de uma integração futura, fora de escopo
    aqui (mesmo padrão do `batman patrol` já usado no `radar-preditivo`)."""
    resultado = ResultadoCicloWatchdog()
    resultado.alertas_sla = verificar_sla_e_alarmar(solicitacoes_human_review, governance)

    for resposta in respostas_humanas_chegadas:
        try:
            retomar_missao(resposta, event_bus, runtime, workflow, decision_engine)
            resultado.missoes_retomadas.append(resposta.mission_id)
        except Exception as exc:  # noqa: BLE001 - falha ao retomar 1 missao nunca derruba o ciclo
            resultado.missoes_com_falha_ao_retomar[resposta.mission_id] = str(exc)

    return resultado
