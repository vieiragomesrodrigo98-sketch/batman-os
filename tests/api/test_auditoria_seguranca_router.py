"""Prova ponta-a-ponta do endpoint `POST /missions/security-audit`
(Fase 6 do roadmap de plataforma, `.claude/plans/peaceful-wondering-
hearth.md`, Estágio 6.3). Mesma doutrina de `tests/reference/
test_security_audit_playbook_e2e.py` (zero mock de Kernel/Runtime/
Capability), agora via requisição HTTP real contra o app."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import batman_os.cli.auditoria_seguranca_command as auditoria_mod
from batman_os.api.app import criar_app
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


class TestEndpointSecurityAudit:
    def test_repo_com_violacoes_detecta_exatamente_as_4_esperadas(self, tmp_path: Path) -> None:
        _plantar_repositorio_com_violacoes(tmp_path)

        with TestClient(criar_app()) as client:
            resposta = client.post(
                "/missions/security-audit", json={"root": str(tmp_path), "tenant_id": "acme"}
            )

        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo["estado_final"] == "completed"
        codigos = {a["codigo"] for a in corpo["achados"]}
        assert codigos == {"CLOUD-001", "DEVOPS-003", "CLOUD-002", "DEP-003"}
        assert corpo["relatorio"]["total_achados"] == 4

    def test_repo_limpo_completa_sem_achados(self, tmp_path: Path) -> None:
        (tmp_path / "api").mkdir()
        (tmp_path / "api" / "app.py").write_text("print('ola mundo')\n", encoding="utf-8")

        with TestClient(criar_app()) as client:
            resposta = client.post("/missions/security-audit", json={"root": str(tmp_path)})

        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo["estado_final"] == "completed"
        assert corpo["achados"] == []

    def test_tenant_id_ausente_usa_local_como_default(self, tmp_path: Path) -> None:
        app = criar_app()
        with TestClient(app) as client:
            resposta = client.post("/missions/security-audit", json={"root": str(tmp_path)})

        assert resposta.status_code == 200
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

        with TestClient(criar_app()) as client:
            chamadas_apos_startup = len(chamadas)
            assert chamadas_apos_startup == 3  # 3 Capabilities certificadas no lifespan

            client.post("/missions/security-audit", json={"root": str(tmp_path)})
            client.post("/missions/security-audit", json={"root": str(tmp_path)})

            assert len(chamadas) == chamadas_apos_startup
