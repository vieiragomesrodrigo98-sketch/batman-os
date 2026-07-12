"""Esqueleto do app FastAPI (Fase 6 do roadmap de plataforma, `.claude/
plans/peaceful-wondering-hearth.md`, Estágios 6.2/6.3, 7.2/7.3).

Reaproveita as funções já públicas de `cli/auditoria_seguranca_
command.py` (Estágios 6.1/6.2) para construir, UMA VEZ no `lifespan` do
processo (não por requisição), os colaboradores caros de montar:
`preparar_capabilities()` (custo de recertificação das Capabilities),
`registro_tipos()`, `construir_decision_engine()`. `EventBus`/
`ExecutionEngine`/`pool_missoes`/`JobStore` são construídos aqui
diretamente pelo mesmo motivo — ver `api/state.py` para o raciocínio
completo de por que cada peça é segura como singleton de processo."""

from __future__ import annotations

from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

from fastapi import FastAPI

from batman_os.api.auth import ApiKeyStore
from batman_os.api.routers.auditoria_seguranca import router as router_auditoria_seguranca
from batman_os.api.routers.jobs import router as router_jobs
from batman_os.api.state import ColaboradoresCompartilhados, JobStore
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


def criar_app(
    db_path: str = ":memory:",
    max_missoes_concorrentes: int = 8,
    api_keys: dict[str, str] | None = None,
) -> FastAPI:
    """`db_path`: mesma convenção de `executar_scan`/`executar_
    auditoria_seguranca` (`":memory:"` default; um caminho real
    persiste os eventos entre restarts do processo — escolha de valor
    em produção é configuração de deploy, fora de escopo aqui).

    `max_missoes_concorrentes` (Fase 7, Estágio 7.2) — tamanho do
    `pool_missoes`, dedicado a rodar Missões inteiras em background,
    NUNCA reaproveitando `ExecutionEngine._executor`/`_supervisor`
    (dimensionados para invocação de UMA Capability — achado de
    investigação: reentrar neles arrisca esgotar o pool sob
    concorrência).

    `api_keys` (Fase 8, Estágio 8.1) — mapa tenant->chave explícito,
    mesmo padrão de `db_path`: `None` (default) carrega de `BATMAN_
    API_KEYS` via `ApiKeyStore.carregar()` (uso real); um dict explícito
    (uso em teste) nunca toca o `.env` real."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        registry, operator = preparar_capabilities()
        app.state.chave_store = (
            ApiKeyStore(api_keys) if api_keys is not None else ApiKeyStore.carregar()
        )
        execution_engine = ExecutionEngine(
            validador_schema=ValidadorSchemaEstrutural(),
            validador_contrato_nao_deterministico=ValidadorContratoSempreAprova(),
        )
        event_bus = EventBus(db_path=db_path)
        pool_missoes = ThreadPoolExecutor(
            max_workers=max_missoes_concorrentes, thread_name_prefix="batman-os-missoes"
        )
        app.state.colaboradores = ColaboradoresCompartilhados(
            registry=registry,
            operator=operator,
            runtime=MissionRuntime(event_bus, tipos=registro_tipos()),
            decision_engine=construir_decision_engine(),
            execution_engine=execution_engine,
            event_bus=event_bus,
            pool_missoes=pool_missoes,
            job_store=JobStore(),
        )
        try:
            yield
        finally:
            execution_engine.fechar()
            pool_missoes.shutdown(wait=False, cancel_futures=True)

    app = FastAPI(title="Batman OS API", lifespan=lifespan)
    app.include_router(router_auditoria_seguranca)
    app.include_router(router_jobs)
    return app
