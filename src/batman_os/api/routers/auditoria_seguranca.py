"""Endpoint `POST /missions/security-audit` (Fase 6 do roadmap de
plataforma, `.claude/plans/peaceful-wondering-hearth.md`, Estágio 6.3).

Handler fino: monta o Playbook POR REQUISIÇÃO (barato — Achado 2 do
plano, `ChecagemDeArquivos` é um dataclass leve sem I/O na construção,
os specs estáticos já foram carregados uma vez) e chama
`executar_missao_via_playbook()` (já 100% amigável a injeção de
dependência — todo colaborador é parâmetro explícito) com os
colaboradores compartilhados do app."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from batman_os.api.dependencies import ColaboradoresDep
from batman_os.api.schemas import AuditoriaSegurancaRequest, AuditoriaSegurancaResponse
from batman_os.cli.auditoria_seguranca_command import TIPO_MISSAO, montar_playbook
from batman_os.foundation.types import OperatorRef, TenantId
from batman_os.kernel.mission_runtime import MissionIntent
from batman_os.orchestration.playbook_driver import executar_missao_via_playbook
from batman_os.workflow.playbooks import PlaybookRegistry

router = APIRouter()


@router.post("/missions/security-audit", response_model=AuditoriaSegurancaResponse)
def executar_security_audit(
    corpo: AuditoriaSegurancaRequest, colaboradores: ColaboradoresDep
) -> AuditoriaSegurancaResponse:
    playbook, especificacoes = montar_playbook(Path(corpo.root))

    playbook_registry = PlaybookRegistry()
    playbook_registry.register(playbook)

    resultado = executar_missao_via_playbook(
        MissionIntent(dados={"tipo": "security-audit"}),
        TIPO_MISSAO,
        TenantId(corpo.tenant_id),
        especificacoes,
        runtime=colaboradores.runtime,
        registro=colaboradores.registry,
        registry=colaboradores.registry,
        decision_engine=colaboradores.decision_engine,
        execution_engine=colaboradores.execution_engine,
        operator=colaboradores.operator,
        operator_ref=OperatorRef(operator_id=colaboradores.operator.id),
        repositorio_playbooks=playbook_registry,
    )

    return AuditoriaSegurancaResponse(
        mission_id=str(resultado.mission_id),
        workflow_run_id=str(resultado.workflow_run_id) if resultado.workflow_run_id else None,
        estado_final=resultado.estado_final,
        achados=resultado.achados,
        relatorio=resultado.relatorio,
    )
