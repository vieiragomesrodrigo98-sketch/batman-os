"""Endpoint `POST /missions/security-audit` (Fase 6 do roadmap de
plataforma, `.claude/plans/peaceful-wondering-hearth.md`, Estágio 6.3;
assíncrono desde a Fase 7, Estágio 7.2; autenticado desde a Fase 8,
Estágio 8.2).

Handler fino: monta o Playbook POR REQUISIÇÃO (barato — Achado 2 do
plano, `ChecagemDeArquivos` é um dataclass leve sem I/O na construção,
os specs estáticos já foram carregados uma vez); cria a Missão de forma
SÍNCRONA via `iniciar_missao_via_playbook()` (rápido — só `runtime.
create()`/`transition()`) para poder devolver o `mission_id` real no
`202` imediatamente; submete a parte potencialmente lenta
(`continuar_missao_via_playbook()`) ao `pool_missoes` dedicado
(`api/state.py`), nunca ao `ExecutionEngine` (achado de investigação:
dimensionado para invocação de UMA Capability, reentrar nele arrisca
esgotar o pool).

`tenant_id: TenantAutenticadoDep` (Fase 8) — nunca mais lido do corpo da
requisição; deriva 100% da chave de API autenticada (`api/auth.py`)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from batman_os.api.auth import TenantAutenticadoDep
from batman_os.api.dependencies import ColaboradoresDep
from batman_os.api.schemas import AuditoriaSegurancaAceito, AuditoriaSegurancaRequest
from batman_os.cli.auditoria_seguranca_command import TIPO_MISSAO, montar_playbook
from batman_os.foundation.types import OperatorRef
from batman_os.kernel.mission_runtime import MissionIntent
from batman_os.orchestration.playbook_driver import (
    continuar_missao_via_playbook,
    iniciar_missao_via_playbook,
)
from batman_os.workflow.playbooks import PlaybookRegistry

router = APIRouter()


@router.post("/missions/security-audit", status_code=202, response_model=AuditoriaSegurancaAceito)
def executar_security_audit(
    corpo: AuditoriaSegurancaRequest,
    colaboradores: ColaboradoresDep,
    tenant_id: TenantAutenticadoDep,
) -> AuditoriaSegurancaAceito:
    playbook, especificacoes = montar_playbook(Path(corpo.root))
    playbook_registry = PlaybookRegistry()
    playbook_registry.register(playbook)

    mission = iniciar_missao_via_playbook(
        MissionIntent(dados={"tipo": "security-audit"}),
        TIPO_MISSAO,
        tenant_id,
        runtime=colaboradores.runtime,
    )

    future = colaboradores.pool_missoes.submit(
        continuar_missao_via_playbook,
        mission,
        especificacoes,
        runtime=colaboradores.runtime,
        registro=colaboradores.registry,
        registry=colaboradores.registry,
        decision_engine=colaboradores.decision_engine,
        execution_engine=colaboradores.execution_engine,
        operator=colaboradores.operator,
        operator_ref=OperatorRef(operator_id=colaboradores.operator.id),
        repositorio_playbooks=playbook_registry,
        event_bus=colaboradores.event_bus,
    )
    colaboradores.job_store.registrar(mission.id, tenant_id, future, especificacoes)
    future.add_done_callback(colaboradores.job_store.callback_de_desfecho(mission.id))

    return AuditoriaSegurancaAceito(mission_id=str(mission.id))
