"""Endpoints `GET /jobs/{mission_id}` + `POST /missions/{mission_id}/
resume` (Fase 7 do roadmap de plataforma, `.claude/plans/peaceful-
wondering-hearth.md`, Estágio 7.3; autenticados desde a Fase 8, Estágio
8.2).

`job_id` = `mission_id` (Achado 1 da Fase 7 — `MissionState` já é a
máquina de estados, não se inventa um `JobId` paralelo). O `DecisionPoint`
pendente devolvido por `GET /jobs/{mission_id}` (quando a Missão está
`AwaitingHuman`) precisa ser ecoado de volta em `POST .../resume` — o
Kernel não persiste isso em lugar nenhum (achado de investigação), só o
`JobStore` (`api/state.py`, junto com `especificacoes_por_indice`, a
outra peça que falta para retomar o Playbook original).

`tenant_id: TenantAutenticadoDep` (Fase 8) — nunca mais lido de query
param/corpo; deriva 100% da chave de API autenticada (`api/auth.py`)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from batman_os.api.auth import TenantAutenticadoDep
from batman_os.api.dependencies import ColaboradoresDep
from batman_os.api.schemas import AuditoriaSegurancaAceito, JobStatusResponse, ResumoRequest
from batman_os.foundation.types import MissionId, OperatorRef
from batman_os.kernel.mission_runtime import MissionState
from batman_os.kernel.planning_engine import DecisionPoint
from batman_os.orchestration.playbook_driver import (
    hidratar_decisao_pendente,
    retomar_missao_apos_escalada,
)

router = APIRouter()


@router.get("/jobs/{mission_id}", response_model=JobStatusResponse)
def consultar_job(
    mission_id: str, tenant_id: TenantAutenticadoDep, colaboradores: ColaboradoresDep
) -> JobStatusResponse:
    mid = MissionId(mission_id)
    missao = colaboradores.runtime.get_mission(mid, tenant_id)
    entrada = colaboradores.job_store.consultar(mid)

    achados: list[dict[str, object]] = []
    relatorio: dict[str, object] | None = None
    decision_pendente: DecisionPoint | None = None
    erro = None
    if entrada is not None:
        if entrada.erro is not None:
            erro = entrada.erro
        elif entrada.resultado is not None:
            achados = entrada.resultado.achados
            relatorio = entrada.resultado.relatorio
            decision_pendente = entrada.resultado.decision_pendente
    elif missao.estado == MissionState.AWAITING_HUMAN:
        # Fase 10, Estagio 10.1 — cache-miss no JobStore (processo
        # reiniciado): sem isso, decision_pendente ficaria `None` mesmo
        # com a Missao genuinamente aguardando humano (Mission.estado
        # sobrevive via EventBus desde a Fase 2, mas o DecisionPoint em
        # si so existia no JobStore em memoria ate esta fase).
        decision_pendente = hidratar_decisao_pendente(colaboradores.event_bus, mid)

    return JobStatusResponse(
        mission_id=str(missao.id),
        estado=missao.estado.value,
        achados=achados,
        relatorio=relatorio,
        decision_pendente=decision_pendente,
        erro=erro,
    )


@router.post(
    "/missions/{mission_id}/resume", status_code=202, response_model=AuditoriaSegurancaAceito
)
def resumir_missao(
    mission_id: str,
    corpo: ResumoRequest,
    colaboradores: ColaboradoresDep,
    tenant_id: TenantAutenticadoDep,
) -> AuditoriaSegurancaAceito:
    mid = MissionId(mission_id)
    missao = colaboradores.runtime.get_mission(mid, tenant_id)

    entrada = colaboradores.job_store.consultar(mid)
    if entrada is None:
        # Job nunca foi submetido nesta instancia do app (ou processo
        # reiniciou) -- sem especificacoes_por_indice nao ha como
        # reconstruir o Playbook original (mesma limitacao documentada
        # em EntradaJob).
        raise HTTPException(
            status_code=409, detail=f"Job {mission_id} desconhecido — nada para retomar"
        )

    future = colaboradores.pool_missoes.submit(
        retomar_missao_apos_escalada,
        missao,
        corpo.ponto,
        entrada.especificacoes_por_indice,
        opcao_escolhida=corpo.opcao_escolhida,
        evidencia=corpo.evidencia,
        runtime=colaboradores.runtime,
        registry=colaboradores.registry,
        decision_engine=colaboradores.decision_engine,
        execution_engine=colaboradores.execution_engine,
        operator=colaboradores.operator,
        operator_ref=OperatorRef(operator_id=colaboradores.operator.id),
        event_bus=colaboradores.event_bus,
    )
    colaboradores.job_store.registrar(mid, tenant_id, future, entrada.especificacoes_por_indice)
    future.add_done_callback(colaboradores.job_store.callback_de_desfecho(mid))

    return AuditoriaSegurancaAceito(mission_id=mission_id)
