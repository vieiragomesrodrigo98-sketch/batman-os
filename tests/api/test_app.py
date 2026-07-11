"""Testes do esqueleto do app FastAPI (Fase 6 do roadmap de plataforma,
`.claude/plans/peaceful-wondering-hearth.md`, Estágio 6.2) — o `lifespan`
constrói os colaboradores compartilhados uma vez, e o `ExecutionEngine`
fecha exatamente uma vez no shutdown, nunca por requisição."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from batman_os.api.app import criar_app
from batman_os.api.state import ColaboradoresCompartilhados
from batman_os.cli.auditoria_seguranca_command import (
    CAP_DEPENDENCIAS_AGREGADOR,
    CAP_REGEX_AGREGADOR,
    CAP_RELATORIO,
)
from batman_os.foundation.types import CapabilityRef
from batman_os.kernel.mission_runtime import MissionRuntime
from batman_os.runtime.execution_engine import ExecutionEngine


def test_lifespan_constroi_colaboradores_compartilhados() -> None:
    app = criar_app()

    with TestClient(app):
        colaboradores = app.state.colaboradores
        assert isinstance(colaboradores, ColaboradoresCompartilhados)
        assert isinstance(colaboradores.runtime, MissionRuntime)

        for capability_id in (CAP_REGEX_AGREGADOR, CAP_DEPENDENCIAS_AGREGADOR, CAP_RELATORIO):
            definicao = colaboradores.registry.resolve(
                CapabilityRef(capability_id=capability_id, versao="1.0.0")
            )
            assert definicao.id == capability_id


def test_lifespan_fecha_execution_engine_exatamente_uma_vez(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chamadas: list[None] = []
    fechar_original = ExecutionEngine.fechar

    def _fechar_espiao(self: ExecutionEngine) -> None:
        chamadas.append(None)
        fechar_original(self)

    monkeypatch.setattr(ExecutionEngine, "fechar", _fechar_espiao)

    app = criar_app()
    with TestClient(app):
        assert chamadas == []

    assert len(chamadas) == 1


def test_duas_instancias_de_app_nao_compartilham_colaboradores() -> None:
    """Cada `criar_app()` constrói seus próprios colaboradores — não há
    estado global entre apps distintos (relevante para testes rodando em
    paralelo/isolados)."""
    app_a, app_b = criar_app(), criar_app()
    with TestClient(app_a), TestClient(app_b):
        assert app_a.state.colaboradores.registry is not app_b.state.colaboradores.registry
