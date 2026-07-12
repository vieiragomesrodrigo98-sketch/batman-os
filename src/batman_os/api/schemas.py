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

from batman_os.foundation.types import DecisionOption, Evidence
from batman_os.kernel.planning_engine import DecisionPoint


class AuditoriaSegurancaRequest(BaseModel):
    """Sem `tenant_id` desde a Fase 8 (autenticação real) — o tenant é
    derivado 100% da chave de API autenticada (`api/auth.py::
    TenantAutenticadoDep`), nunca mais alegado pelo chamador."""

    root: str


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


class JobStatusResponse(BaseModel):
    """Resposta de `GET /jobs/{mission_id}` (Fase 7, Estágio 7.3).

    `decision_pendente` (o `DecisionPoint` que causou a escalada, quando
    `estado == "AwaitingHuman"`) reaproveita o modelo Pydantic de domínio
    `DecisionPoint` DIRETAMENTE como contrato JSON — deliberado, evita
    duplicar campo a campo num schema HTTP paralelo que poderia divergir
    do modelo real. Mesmo raciocínio para `ResumoRequest` abaixo."""

    mission_id: str
    estado: str
    achados: list[dict[str, Any]] = Field(default_factory=list)
    relatorio: dict[str, Any] | None = None
    decision_pendente: DecisionPoint | None = None
    erro: str | None = None


class ResumoRequest(BaseModel):
    """Corpo de `POST /missions/{mission_id}/resume` (Fase 7, Estágio
    7.3) — `ponto` é o MESMO `DecisionPoint` devolvido por `GET /jobs/
    {mission_id}` quando `estado == "AwaitingHuman"`; o chamador o ecoa
    de volta (o Kernel não persiste o `DecisionPoint` pendente em lugar
    nenhum — achado de investigação da Fase 7, ver `JobStore`).

    Sem `workflow_run_id` (existe em `RespostaHumanaChegada`, o modelo
    de domínio, mas não aqui): o único cenário que `playbook_driver.py`
    produz hoje é escalada ANTES do `WorkflowEngine` existir (Estágio
    7.1) — nunca há um `WorkflowRun` prévio para referenciar. Incluir o
    campo seria enganoso (sugeriria que o chamador precisa obtê-lo de
    algum lugar que não existe).

    Sem `tenant_id` desde a Fase 8 (mesmo raciocínio de
    `AuditoriaSegurancaRequest`) — derivado da chave de API autenticada."""

    ponto: DecisionPoint
    opcao_escolhida: DecisionOption
    evidencia: list[Evidence]
