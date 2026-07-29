"""Testes de `cli/batman.py::main` — resolve a referência de entry point
declarada em `pyproject.toml` (`batman_os.cli.batman:main`)."""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

import pytest

from batman_os.cli.batman import main
from batman_os.foundation.types import TenantId
from batman_os.governance.inbox import InboxStore, OrigemAchado, StatusAchadoInbox


class TestComandoScan:
    def test_repo_vazio_sem_fail_on_retorna_zero(self, tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
        codigo = main(["scan", "--root", str(tmp_path)])

        assert codigo == 0
        saida = capsys.readouterr().out
        assert "VPS-001" in saida
        assert "achado(s)" in saida

    def test_fail_on_high_retorna_1_quando_ha_achado_high(self, tmp_path: Path) -> None:
        codigo = main(["scan", "--root", str(tmp_path), "--fail-on", "high"])

        assert codigo == 1  # VPS-001 e "high" mesmo em repo vazio

    def test_fail_on_critical_retorna_0_sem_achado_critical(self, tmp_path: Path) -> None:
        codigo = main(["scan", "--root", str(tmp_path), "--fail-on", "critical"])

        assert codigo == 0  # so ha achados high/medium no repo vazio, nenhum critical

    def test_sem_subcomando_levanta_erro_de_argparse(self) -> None:
        try:
            main([])
        except SystemExit as exc:
            assert exc.code != 0
        else:
            raise AssertionError("esperava SystemExit sem subcomando")


class TestMilestone5OpcaoDb:
    """Achado de revisão fechado na Milestone 5: `--db` persiste o log de
    eventos do scan entre execuções, em vez de descartá-lo sempre ao final."""

    def test_sem_db_explicito_cria_estado_db_relativo_ao_root(self, tmp_path: Path) -> None:
        main(["scan", "--root", str(tmp_path)])

        assert (tmp_path / ".batman-os" / "estado.db").exists()

    def test_db_memory_explicito_nao_cria_arquivo_algum(self, tmp_path: Path) -> None:
        main(["scan", "--root", str(tmp_path), "--db", ":memory:"])

        assert not (tmp_path / ".batman-os").exists()

    def test_db_customizado_e_reaproveitado_entre_execucoes(self, tmp_path: Path) -> None:
        db_path = tmp_path / "meu_estado.db"

        main(["scan", "--root", str(tmp_path), "--db", str(db_path)])
        assert db_path.exists()

        tamanho_apos_primeira = db_path.stat().st_size
        main(["scan", "--root", str(tmp_path), "--db", str(db_path)])

        assert db_path.stat().st_size >= tamanho_apos_primeira


def _tenants_das_missoes_criadas(db_path: Path) -> set[str]:
    conn = sqlite3.connect(str(db_path))
    try:
        linhas = conn.execute(
            "SELECT payload_json FROM events WHERE payload_json LIKE '%MissionCreated%'"
        ).fetchall()
    finally:
        conn.close()
    return {json.loads(linha[0])["tenant_id"] for linha in linhas}


class TestInboxIntegracaoScan:
    """Integracao `batman scan` -> inbox (`governance/inbox.py`), com
    arvore sintetica (repo vazio ja dispara VPS-001, severidade 'high' —
    ver `TestComandoScan` acima). Ponto 4 do pacote."""

    def test_scan_grava_no_inbox_por_padrao(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        main(["scan", "--root", str(tmp_path)])

        saida = capsys.readouterr().out
        assert "inbox:" in saida

        db_path = str(tmp_path / ".batman-os" / "estado.db")
        with InboxStore(db_path) as store:
            achados = store.listar()
        assert len(achados) >= 1
        assert all(a.origem == OrigemAchado.SCAN for a in achados)

    def test_scan_com_db_memory_nao_grava_no_inbox(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        main(["scan", "--root", str(tmp_path), "--db", ":memory:"])

        saida = capsys.readouterr().out
        assert "inbox:" not in saida
        assert not (tmp_path / ".batman-os").exists()

    def test_rescan_do_mesmo_repo_faz_upsert_sem_duplicar(self, tmp_path: Path) -> None:
        main(["scan", "--root", str(tmp_path)])
        db_path = str(tmp_path / ".batman-os" / "estado.db")
        with InboxStore(db_path) as store:
            total_apos_primeiro = len(store.listar())

        main(["scan", "--root", str(tmp_path)])
        with InboxStore(db_path) as store:
            total_apos_segundo = len(store.listar())

        assert total_apos_segundo == total_apos_primeiro

    def test_scan_com_tenant_customizado_propaga_para_o_inbox(self, tmp_path: Path) -> None:
        db_path = tmp_path / "estado.db"
        main(["scan", "--root", str(tmp_path), "--db", str(db_path), "--tenant", "acme"])

        with InboxStore(str(db_path)) as store:
            achados = store.listar(tenant_id=TenantId("acme"))
        assert len(achados) >= 1


class TestInboxCliList:
    def _rodar_scan(self, tmp_path: Path) -> Path:
        db_path = tmp_path / "estado.db"
        main(["scan", "--root", str(tmp_path), "--db", str(db_path)])
        return db_path

    def test_list_vazio(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        db_path = tmp_path / "vazio.db"
        codigo = main(["inbox", "list", "--db", str(db_path)])

        assert codigo == 0
        saida = capsys.readouterr().out
        assert "0 achado(s)" in saida

    def test_list_apos_scan_mostra_achados(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db_path = self._rodar_scan(tmp_path)
        capsys.readouterr()  # descarta a saida do scan

        codigo = main(["inbox", "list", "--db", str(db_path)])

        assert codigo == 0
        saida = capsys.readouterr().out
        assert "achado(s)" in saida
        assert "(scan/novo)" in saida

    def test_list_sem_subcomando_levanta_erro_de_argparse(self) -> None:
        with pytest.raises(SystemExit):
            main(["inbox"])


class TestInboxCliAckDefer:
    def _semear_e_pegar_id(self, tmp_path: Path) -> tuple[Path, str]:
        db_path = tmp_path / "estado.db"
        main(["scan", "--root", str(tmp_path), "--db", str(db_path)])
        with InboxStore(str(db_path)) as store:
            achado_id = store.listar()[0].id
        return db_path, achado_id

    def test_ack_marca_tratado(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        db_path, achado_id = self._semear_e_pegar_id(tmp_path)
        capsys.readouterr()

        codigo = main(["inbox", "ack", achado_id, "--db", str(db_path), "--nota", "fix aplicado"])

        assert codigo == 0
        assert "tratado:" in capsys.readouterr().out
        with InboxStore(str(db_path)) as store:
            assert store.obter(achado_id).status == StatusAchadoInbox.TRATADO

    def test_defer_marca_deferido(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        db_path, achado_id = self._semear_e_pegar_id(tmp_path)
        capsys.readouterr()

        codigo = main(
            ["inbox", "defer", achado_id, "--db", str(db_path), "--nota", "aceito o risco por ora"]
        )

        assert codigo == 0
        assert "deferido:" in capsys.readouterr().out
        with InboxStore(str(db_path)) as store:
            assert store.obter(achado_id).status == StatusAchadoInbox.DEFERIDO

    def test_ack_sem_flag_nota_e_erro_de_argparse(self, tmp_path: Path) -> None:
        db_path, achado_id = self._semear_e_pegar_id(tmp_path)
        with pytest.raises(SystemExit):
            main(["inbox", "ack", achado_id, "--db", str(db_path)])

    def test_ack_com_nota_vazia_retorna_1_e_nao_muda_status(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db_path, achado_id = self._semear_e_pegar_id(tmp_path)
        capsys.readouterr()

        codigo = main(["inbox", "ack", achado_id, "--db", str(db_path), "--nota", "  "])

        assert codigo == 1
        assert "erro:" in capsys.readouterr().out
        with InboxStore(str(db_path)) as store:
            assert store.obter(achado_id).status == StatusAchadoInbox.NOVO

    def test_ack_de_id_desconhecido_retorna_1(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db_path, _ = self._semear_e_pegar_id(tmp_path)
        capsys.readouterr()

        codigo = main(["inbox", "ack", "id-fantasma", "--db", str(db_path), "--nota", "x"])

        assert codigo == 1
        assert "erro:" in capsys.readouterr().out


class TestFase5Estagio53FlagTenant:
    """Fase 5 do roadmap de plataforma (isolamento multi-tenant,
    `.claude/plans/peaceful-wondering-hearth.md`), Estagio 5.3 — `--tenant`
    substitui o `TENANT_PADRAO` hardcoded que toda Missao de scan usava."""

    def test_flag_tenant_e_usada_nas_missoes_criadas(self, tmp_path: Path) -> None:
        db_path = tmp_path / "estado.db"

        main(["scan", "--root", str(tmp_path), "--db", str(db_path), "--tenant", "acme"])

        assert _tenants_das_missoes_criadas(db_path) == {"acme"}

    def test_sem_flag_tenant_preserva_o_default_local(self, tmp_path: Path) -> None:
        db_path = tmp_path / "estado.db"

        main(["scan", "--root", str(tmp_path), "--db", str(db_path)])

        assert _tenants_das_missoes_criadas(db_path) == {"local"}


class TestFlagsDeExclusaoDeDiretorios:
    """`--exclude NOME` (repetivel, soma aos defaults) e `--no-default-
    excludes` (escape hatch) -- ver `descoberta_arquivos.py::
    DEFAULT_EXCLUDED_DIRS`. A poda em si esta testada em unidade em
    `tests/cli/test_descoberta_arquivos.py`; aqui e so o parsing/plumbing
    da CLI ate `executar_scan`."""

    def test_exclude_repetivel_chega_ate_o_log_de_descoberta(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        (tmp_path / "vendor").mkdir()
        (tmp_path / "vendor" / "a.py").write_text("x", encoding="utf-8")
        (tmp_path / "terceiros").mkdir()
        (tmp_path / "terceiros" / "b.py").write_text("y", encoding="utf-8")

        with caplog.at_level(logging.INFO, logger="batman_os.cli.scan_command"):
            codigo = main(
                [
                    "scan",
                    "--root",
                    str(tmp_path),
                    "--db",
                    ":memory:",
                    "--exclude",
                    "vendor",
                    "--exclude",
                    "terceiros",
                ]
            )

        assert codigo == 0
        mensagens = " ".join(registro.message for registro in caplog.records)
        assert "'vendor'" in mensagens
        assert "'terceiros'" in mensagens

    def test_no_default_excludes_e_aceito_sem_crashar(self, tmp_path: Path) -> None:
        (tmp_path / ".venv").mkdir()
        (tmp_path / ".venv" / "a.py").write_text("x", encoding="utf-8")

        codigo = main(
            ["scan", "--root", str(tmp_path), "--db", ":memory:", "--no-default-excludes"]
        )

        assert codigo == 0

    def test_no_default_excludes_desliga_a_poda_padrao_no_log(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        (tmp_path / ".venv").mkdir()
        (tmp_path / ".venv" / "a.py").write_text("x", encoding="utf-8")

        with caplog.at_level(logging.INFO, logger="batman_os.cli.scan_command"):
            main(["scan", "--root", str(tmp_path), "--db", ":memory:", "--no-default-excludes"])

        mensagens = " ".join(registro.message for registro in caplog.records)
        assert "0 diretorio(s) podado(s)" in mensagens

    def test_sem_flag_exclude_o_default_continua_valendo(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        (tmp_path / ".venv").mkdir()
        (tmp_path / ".venv" / "a.py").write_text("x", encoding="utf-8")

        with caplog.at_level(logging.INFO, logger="batman_os.cli.scan_command"):
            codigo = main(["scan", "--root", str(tmp_path), "--db", ":memory:"])

        assert codigo == 0
        mensagens = " ".join(registro.message for registro in caplog.records)
        assert "1 diretorio(s) podado(s)" in mensagens
