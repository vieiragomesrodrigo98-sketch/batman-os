"""Testes de `cli/batman.py::main` — resolve a referência de entry point
declarada em `pyproject.toml` (`batman_os.cli.batman:main`)."""

from __future__ import annotations

from pathlib import Path

from batman_os.cli.batman import main


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
