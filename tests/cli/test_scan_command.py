"""Testes de `cli/scan_command.py::executar_scan` — o orquestrador real do
primeiro lote de Capabilities migradas, contra repositórios sintéticos.

Estes testes passam `especificacoes=carregar_lote_01()` explicitamente (em
vez de deixar `executar_scan` usar o padrão de todos os lotes) para
permanecerem deterministas conforme mais lotes são migrados (Milestone 2+)
— sem isso, cada novo lote poderia fazer mais regras dispararem no mesmo
repositório sintético e quebrar as contagens exatas abaixo."""

from __future__ import annotations

from pathlib import Path

from batman_os.capabilities.rules.lote_01 import carregar_lote_01
from batman_os.cli.scan_command import executar_scan


class TestExecutarScanRepoVazio:
    """Num repo vazio, só as regras que disparam por AUSENCIA de algo
    (sem depender de nenhum arquivo existir) devem produzir achado."""

    def test_apenas_vps001_e_de002_disparam(self, tmp_path: Path) -> None:
        resultado = executar_scan(tmp_path, especificacoes=carregar_lote_01())

        codigos = {achado.codigo for achado in resultado.achados}
        assert codigos == {"VPS-001", "DE-002"}

    def test_vps002_nao_dispara_sem_o_arquivo_base(self, tmp_path: Path) -> None:
        resultado = executar_scan(tmp_path, especificacoes=carregar_lote_01())

        assert "VPS-002" not in {achado.codigo for achado in resultado.achados}

    def test_cloud007_nao_dispara_sem_nenhum_dockerfile(self, tmp_path: Path) -> None:
        resultado = executar_scan(tmp_path, especificacoes=carregar_lote_01())

        assert "CLOUD-007" not in {achado.codigo for achado in resultado.achados}


class TestExecutarScanComGatilhosReais:
    def test_devops003_red007_fe004_disparam_junto_com_os_de_repo_vazio(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / ".env").write_text("X=1", encoding="utf-8")
        (tmp_path / ".gitignore").write_text("node_modules/\n", encoding="utf-8")

        (tmp_path / "api").mkdir()
        (tmp_path / "api" / "config_ruim.py").write_text(
            "SECRET_KEY = 'valor-literal-de-verdade'\n", encoding="utf-8"
        )

        (tmp_path / "frontend" / "src").mkdir(parents=True)
        (tmp_path / "frontend" / "src" / "App.ts").write_text(
            "console.log('debug')\n", encoding="utf-8"
        )

        resultado = executar_scan(tmp_path, especificacoes=carregar_lote_01())

        codigos = {achado.codigo for achado in resultado.achados}
        assert codigos == {"VPS-001", "DE-002", "DEVOPS-003", "RED-007", "FE-004"}

    def test_vps002_dispara_quando_arquivo_existe_sem_a_flag(self, tmp_path: Path) -> None:
        (tmp_path / ".env.production.example").write_text("OUTRA_VAR=1\n", encoding="utf-8")

        resultado = executar_scan(tmp_path, especificacoes=carregar_lote_01())

        codigos = {achado.codigo for achado in resultado.achados}
        assert "VPS-001" not in codigos  # arquivo agora existe
        assert "VPS-002" in codigos  # mas sem ENABLE_REAL_TRADING=false

    def test_achado_carrega_o_julgamento_embutido_da_regra(self, tmp_path: Path) -> None:
        resultado = executar_scan(tmp_path, especificacoes=carregar_lote_01())

        vps001 = next(a for a in resultado.achados if a.codigo == "VPS-001")
        assert vps001.severidade == "high"
        assert vps001.agente == "vps-infra"
        assert vps001.fingerprint  # nao vazio

    def test_contagem_por_severidade(self, tmp_path: Path) -> None:
        resultado = executar_scan(tmp_path, especificacoes=carregar_lote_01())

        contagem = resultado.contagem_por_severidade()
        assert contagem == {"high": 1, "medium": 1}


class TestExecutarScanComTodosOsLotes:
    """Sem `especificacoes` explícito, `executar_scan` usa a união de todos
    os lotes já migrados — cobertura mínima de que isso não quebra."""

    def test_roda_sem_erro_e_encontra_pelo_menos_os_achados_do_lote_01(
        self, tmp_path: Path
    ) -> None:
        resultado = executar_scan(tmp_path)

        codigos = {achado.codigo for achado in resultado.achados}
        assert {"VPS-001", "DE-002"}.issubset(codigos)

    def test_arquivo_python_nao_crasha_com_todas_as_skills_registradas(
        self, tmp_path: Path
    ) -> None:
        """Achado de auditoria (validacao final Milestones 2-7): as 8
        Capabilities da Milestone 3 (ast_padrao_ausente, ast_kwarg_ausente,
        git_comando_interpretado, execucao_comando_interpretada,
        toml_dependencias, de003, ora005, ora004) compartilham o mesmo
        conjunto de nomes de campo na entrada (`tipo, caminho, conteudo,
        regra`) — um `.py` real, escaneado com TODOS os lotes registrados
        simultaneamente (como acontece de verdade via `executar_scan` sem
        `especificacoes` explicito), antes gerava um plano de 8 passos por
        arquivo (`CapabilityRegistry.find_candidates` empatando as 8 como
        candidatas) e crashava com `EntradaNaoRegistrada` ao tentar invocar
        o segundo passo — `scan_command.py` so registra entrada para o
        passo 0. Fixado em `capability_engine._schema_compativel` (checa o
        valor de campos `const`, nao so a presenca da chave)."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "exemplo.py").write_text("class Foo:\n    pass\n", encoding="utf-8")

        resultado = executar_scan(tmp_path)  # nao deve levantar EntradaNaoRegistrada

        assert resultado is not None
