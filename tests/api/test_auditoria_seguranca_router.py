"""Prova ponta-a-ponta do endpoint `POST /missions/security-audit`
(Fase 6 do roadmap de plataforma, `.claude/plans/peaceful-wondering-
hearth.md`, Estágio 6.3; assíncrono desde a Fase 7, Estágio 7.2). Mesma
doutrina de `tests/reference/test_security_audit_playbook_e2e.py` (zero
mock de Kernel/Runtime/Capability), agora via requisição HTTP real
contra o app."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import batman_os.api.routers.auditoria_seguranca as router_mod
import batman_os.cli.auditoria_seguranca_command as auditoria_mod
from batman_os.api.app import criar_app
from batman_os.api.state import EntradaJob, JobStore
from batman_os.foundation.types import MissionId, TenantId


def _plantar_repositorio_com_violacoes(root: Path) -> None:
    """Mesmo repositório sintético de `test_security_audit_playbook_
    e2e.py` (Fase 3, Estágio 3.4) — 4 violações reais (CLOUD-001,
    DEVOPS-003, CLOUD-002, DEP-003) + 2 checagens deliberadamente
    limpas (RED-007, DEVOPS-004)."""
    (root / "api").mkdir(parents=True)
    (root / "api" / "config.py").write_text("AWS_KEY = 'AKIAABCDEFGHIJKLMNOP'\n", encoding="utf-8")
    (root / ".env").write_text("SECRET=x\n", encoding="utf-8")
    (root / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    (root / "Dockerfile").write_text(
        'FROM python:3.11\nCMD ["python", "app.py"]\n', encoding="utf-8"
    )
    (root / "pyproject.toml").write_text(
        '[project]\nname = "smoke"\nversion = "0.1.0"\ndependencies = ["fastapi>=0.100"]\n',
        encoding="utf-8",
    )


def _aguardar_job(app: FastAPI, mission_id: MissionId, timeout: float = 5.0) -> EntradaJob:
    """Fase 7, Estágio 7.2 — o `GET /jobs/{id}` só chega no Estágio 7.3;
    até lá, os testes fazem polling direto no `JobStore` interno do app
    (mesmo dado que o endpoint futuro vai expor, só sem a camada HTTP)."""
    job_store: JobStore = app.state.colaboradores.job_store  # app.state e dinamico (Any)
    prazo = time.monotonic() + timeout
    while time.monotonic() < prazo:
        entrada = job_store.consultar(mission_id)
        if entrada is not None and (entrada.resultado is not None or entrada.erro is not None):
            return entrada
        time.sleep(0.01)
    raise AssertionError(f"job {mission_id} nao terminou em {timeout}s")


class TestEndpointSecurityAudit:
    def test_repo_com_violacoes_detecta_exatamente_as_4_esperadas(self, tmp_path: Path) -> None:
        _plantar_repositorio_com_violacoes(tmp_path)
        app = criar_app()

        with TestClient(app) as client:
            resposta = client.post(
                "/missions/security-audit", json={"root": str(tmp_path), "tenant_id": "acme"}
            )
            assert resposta.status_code == 202
            mission_id = MissionId(resposta.json()["mission_id"])

            entrada = _aguardar_job(app, mission_id)

        assert entrada.erro is None
        assert entrada.resultado is not None
        assert entrada.resultado.estado_final == "completed"
        codigos = {a["codigo"] for a in entrada.resultado.achados}
        assert codigos == {"CLOUD-001", "DEVOPS-003", "CLOUD-002", "DEP-003"}
        assert entrada.resultado.relatorio is not None
        assert entrada.resultado.relatorio["total_achados"] == 4

    def test_repo_limpo_completa_sem_achados(self, tmp_path: Path) -> None:
        (tmp_path / "api").mkdir()
        (tmp_path / "api" / "app.py").write_text("print('ola mundo')\n", encoding="utf-8")
        app = criar_app()

        with TestClient(app) as client:
            resposta = client.post("/missions/security-audit", json={"root": str(tmp_path)})
            assert resposta.status_code == 202
            mission_id = MissionId(resposta.json()["mission_id"])

            entrada = _aguardar_job(app, mission_id)

        assert entrada.erro is None
        assert entrada.resultado is not None
        assert entrada.resultado.estado_final == "completed"
        assert entrada.resultado.achados == []

    def test_tenant_id_ausente_usa_local_como_default(self, tmp_path: Path) -> None:
        app = criar_app()
        with TestClient(app) as client:
            resposta = client.post("/missions/security-audit", json={"root": str(tmp_path)})

        assert resposta.status_code == 202
        mission_id = MissionId(resposta.json()["mission_id"])
        missao = app.state.colaboradores.runtime.get_mission(mission_id, TenantId("local"))
        assert missao.tenant_id == "local"

    def test_tenant_id_customizado_e_aplicado_na_missao(self, tmp_path: Path) -> None:
        app = criar_app()
        with TestClient(app) as client:
            resposta = client.post(
                "/missions/security-audit", json={"root": str(tmp_path), "tenant_id": "acme"}
            )

            mission_id = MissionId(resposta.json()["mission_id"])
            missao = app.state.colaboradores.runtime.get_mission(mission_id, TenantId("acme"))
            assert missao.tenant_id == "acme"

    def test_segunda_requisicao_nao_recertifica_capabilities(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Prova que os colaboradores do `lifespan` (Estágio 6.2) são de
        fato reaproveitados — a certificação (cara) roda só uma vez no
        startup, nunca de novo por requisição."""
        chamadas: list[None] = []
        # Acessa o simbolo importado dentro do modulo sob teste (nao
        # reexportado explicitamente) de proposito: o monkeypatch precisa
        # substituir "certificar" no NAMESPACE onde auditoria_seguranca_
        # command.py o usa, nao no modulo de origem.
        original = auditoria_mod.certificar  # type: ignore[attr-defined]

        def _certificar_espiao(*args: object, **kwargs: object) -> object:
            chamadas.append(None)
            return original(*args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(auditoria_mod, "certificar", _certificar_espiao)

        app = criar_app()
        with TestClient(app) as client:
            chamadas_apos_startup = len(chamadas)
            assert chamadas_apos_startup == 3  # 3 Capabilities certificadas no lifespan

            r1 = client.post("/missions/security-audit", json={"root": str(tmp_path)})
            r2 = client.post("/missions/security-audit", json={"root": str(tmp_path)})
            _aguardar_job(app, MissionId(r1.json()["mission_id"]))
            _aguardar_job(app, MissionId(r2.json()["mission_id"]))

            assert len(chamadas) == chamadas_apos_startup


class TestFase7Estagio72RespostaAssincrona:
    """Fase 7 do roadmap de plataforma (`.claude/plans/peaceful-
    wondering-hearth.md`), Estágio 7.2."""

    def test_job_aparece_no_store_logo_apos_o_submit(self, tmp_path: Path) -> None:
        (tmp_path / "api").mkdir()
        (tmp_path / "api" / "app.py").write_text("print('ola mundo')\n", encoding="utf-8")
        app = criar_app()

        with TestClient(app) as client:
            resposta = client.post("/missions/security-audit", json={"root": str(tmp_path)})
            mission_id = MissionId(resposta.json()["mission_id"])

            # Consultado ANTES de qualquer polling/espera — a entrada ja
            # precisa existir (resultado pode ou nao estar pronto ainda,
            # dependendo de quao rapido a thread do pool rodou).
            entrada_imediata = app.state.colaboradores.job_store.consultar(mission_id)
            assert entrada_imediata is not None
            assert entrada_imediata.tenant_id == "local"

            _aguardar_job(app, mission_id)

    def test_resposta_202_nao_espera_a_missao_terminar(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Prova que o handler NÃO bloqueia — se bloqueasse, o `POST`
        demoraria pelo menos o tempo do atraso artificial injetado
        abaixo (0.2s); a resposta real chega em uma fração disso."""
        (tmp_path / "api").mkdir()
        (tmp_path / "api" / "app.py").write_text("print('ola mundo')\n", encoding="utf-8")

        # Mesmo padrao de auditoria_mod.certificar acima: acessa o simbolo
        # importado dentro do modulo sob teste, nao reexportado
        # explicitamente, para o monkeypatch valer no NAMESPACE certo.
        original = router_mod.continuar_missao_via_playbook  # type: ignore[attr-defined]

        def _continuar_com_atraso(*args: object, **kwargs: object) -> object:
            time.sleep(0.2)
            return original(*args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(router_mod, "continuar_missao_via_playbook", _continuar_com_atraso)

        app = criar_app()
        with TestClient(app) as client:
            inicio = time.monotonic()
            resposta = client.post("/missions/security-audit", json={"root": str(tmp_path)})
            duracao_da_resposta = time.monotonic() - inicio

            assert resposta.status_code == 202
            assert duracao_da_resposta < 0.1  # bem menor que o atraso de 0.2s injetado

            _aguardar_job(app, MissionId(resposta.json()["mission_id"]), timeout=2.0)

    def test_excecao_nao_tratada_em_background_e_registrada_como_erro_no_job(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """`EntradaJob.erro` (ver docstring) — sem isso, uma exceção
        escapando de `continuar_missao_via_playbook` dentro do
        `pool_missoes` faria o job ficar "em andamento" para sempre
        (`add_done_callback` engole exceções não tratadas em silêncio)."""

        def _continuar_falha(*args: object, **kwargs: object) -> object:
            del args, kwargs
            raise ValueError("falha proposital de teste")

        monkeypatch.setattr(router_mod, "continuar_missao_via_playbook", _continuar_falha)

        app = criar_app()
        with TestClient(app) as client:
            resposta = client.post("/missions/security-audit", json={"root": str(tmp_path)})
            assert resposta.status_code == 202

            entrada = _aguardar_job(app, MissionId(resposta.json()["mission_id"]))

        assert entrada.resultado is None
        assert entrada.erro is not None
        assert "falha proposital de teste" in entrada.erro
