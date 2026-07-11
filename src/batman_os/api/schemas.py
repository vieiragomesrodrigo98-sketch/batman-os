"""Contratos JSON do app FastAPI (Fase 6 do roadmap de plataforma,
`.claude/plans/peaceful-wondering-hearth.md`, Estágio 6.2).

`tenant_id` no corpo da requisição (não em cabeçalho de autenticação) é
deliberado — mesmo padrão do `--tenant` da CLI (Fase 5): NÃO é
autenticação real (nenhum mecanismo de prova de identidade existe nesta
fase, gap documentado no plano), só seleção explícita de tenant.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AuditoriaSegurancaRequest(BaseModel):
    root: str
    tenant_id: str = "local"


class AuditoriaSegurancaAceito(BaseModel):
    """Resposta do `202` (Fase 7, Estágio 7.2) — `mission_id` é o
    `job_id` (Achado 1 da Fase 7: `MissionState` já é a máquina de
    estados, não se inventa um `JobId` paralelo). Consultar o resultado
    via `GET /jobs/{mission_id}` (Estágio 7.3)."""

    mission_id: str


class AuditoriaSegurancaResponse(BaseModel):
    """`workflow_run_id` opcional desde a Fase 7, Estágio 7.1 — uma
    Missão que escala para humano antes do `WorkflowEngine` ser criado
    não tem nenhum `WorkflowRun` ainda (ver `orchestration/
    playbook_driver.py::ResultadoMissaoPlaybook`)."""

    mission_id: str
    workflow_run_id: str | None = None
    estado_final: str
    achados: list[dict[str, Any]] = Field(default_factory=list)
    relatorio: dict[str, Any] | None = None
