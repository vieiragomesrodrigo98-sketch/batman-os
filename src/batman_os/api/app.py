"""Esqueleto do app FastAPI (Fase 6 do roadmap de plataforma, `.claude/
plans/peaceful-wondering-hearth.md`, Estágios 6.2/6.3).

Reaproveita as funções já públicas de `cli/auditoria_seguranca_
command.py` (Estágios 6.1/6.2) para construir, UMA VEZ no `lifespan` do
processo (não por requisição), os colaboradores caros de montar:
`preparar_capabilities()` (custo de recertificação das Capabilities),
`registro_tipos()`, `construir_decision_engine()`. `EventBus`/
`ExecutionEngine` são construídos aqui diretamente pelo mesmo motivo —
ver `api/state.py` para o raciocínio completo de por que cada peça é
segura como singleton de processo."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from batman_os.api.routers.auditoria_seguranca import router as router_auditoria_seguranca
from batman_os.api.state import ColaboradoresCompartilhados
from batman_os.cli.auditoria_seguranca_command import (
    construir_decision_engine,
    preparar_capabilities,
    registro_tipos,
)
from batman_os.kernel.event_bus import EventBus
from batman_os.kernel.mission_runtime import MissionRuntime
from batman_os.orchestration.schema_validators import (
    ValidadorContratoSempreAprova,
    ValidadorSchemaEstrutural,
)
from batman_os.runtime.execution_engine import ExecutionEngine


def criar_app(db_path: str = ":memory:") -> FastAPI:
    """`db_path`: mesma convenção de `executar_scan`/`executar_
    auditoria_seguranca` (`":memory:"` default; um caminho real
    persiste os eventos entre restarts do processo — escolha de valor
    em produção é configuração de deploy, fora de escopo aqui)."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        registry, operator = preparar_capabilities()
        execution_engine = ExecutionEngine(
            validador_schema=ValidadorSchemaEstrutural(),
            validador_contrato_nao_deterministico=ValidadorContratoSempreAprova(),
        )
        app.state.colaboradores = ColaboradoresCompartilhados(
            registry=registry,
            operator=operator,
            runtime=MissionRuntime(EventBus(db_path=db_path), tipos=registro_tipos()),
            decision_engine=construir_decision_engine(),
            execution_engine=execution_engine,
        )
        try:
            yield
        finally:
            execution_engine.fechar()

    app = FastAPI(title="Batman OS API", lifespan=lifespan)
    app.include_router(router_auditoria_seguranca)
    return app
