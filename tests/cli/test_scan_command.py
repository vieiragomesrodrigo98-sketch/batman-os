"""Testes de `cli/scan_command.py::executar_scan` — o orquestrador real do
primeiro lote de Capabilities migradas, contra repositórios sintéticos.

Estes testes passam `especificacoes=carregar_lote_01()` explicitamente (em
vez de deixar `executar_scan` usar o padrão de todos os lotes) para
permanecerem deterministas conforme mais lotes são migrados (Milestone 2+)
— sem isso, cada novo lote poderia fazer mais regras dispararem no mesmo
repositório sintético e quebrar as contagens exatas abaixo."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from batman_os.capabilities.rules.lote_01 import carregar_lote_01
from batman_os.cli.scan_command import (
    AchadoScan,
    ResultadoScan,
    achados_para_inbox,
    executar_scan,
)
from batman_os.foundation.types import Criticidade


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


class TestResumoDePerformance:
    """Fase 1 do roadmap de plataforma ("Capability Timeline") — os
    tempos vem direto do `StepResult` que o Workflow Engine ja mede
    nativamente, so a agregacao por Capability e nova."""

    def test_duracoes_agregadas_por_capability(self, tmp_path: Path) -> None:
        resultado = executar_scan(tmp_path, especificacoes=carregar_lote_01())

        assert "regex-sobre-conteudo-de-arquivo" in resultado.duracoes_por_capability
        duracoes = resultado.duracoes_por_capability["regex-sobre-conteudo-de-arquivo"]
        assert len(duracoes) > 0
        assert all(d >= 0 for d in duracoes)

    def test_resumo_de_performance_agrega_chamadas_total_media_max(self, tmp_path: Path) -> None:
        resultado = executar_scan(tmp_path, especificacoes=carregar_lote_01())

        resumo = resultado.resumo_de_performance()
        stats = resumo["regex-sobre-conteudo-de-arquivo"]
        duracoes = resultado.duracoes_por_capability["regex-sobre-conteudo-de-arquivo"]

        assert stats["chamadas"] == len(duracoes)
        assert stats["total_ms"] == sum(duracoes)
        assert stats["media_ms"] == sum(duracoes) / len(duracoes)
        assert stats["max_ms"] == max(duracoes)


class TestFase2Estagio24ScanParalelo:
    """Fase 2 do roadmap de plataforma (`.claude/plans/peaceful-wondering-
    hearth.md`), Estagio 2.4 — `paralelo=True` e opt-in (default `False`
    preserva o caminho sequencial anterior, ja coberto pelos testes acima);
    quando ativado, produz o MESMO conjunto de achados que o sequencial."""

    def test_paralelo_produz_o_mesmo_conjunto_de_achados_que_sequencial(
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

        sequencial = executar_scan(tmp_path, especificacoes=carregar_lote_01())
        paralelo = executar_scan(tmp_path, especificacoes=carregar_lote_01(), paralelo=True)

        codigos_sequencial = {a.codigo for a in sequencial.achados}
        codigos_paralelo = {a.codigo for a in paralelo.achados}
        assert codigos_paralelo == codigos_sequencial
        assert len(paralelo.achados) == len(sequencial.achados)

    def test_paralelo_sem_erro_com_todos_os_lotes(self, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "exemplo.py").write_text("class Foo:\n    pass\n", encoding="utf-8")

        resultado = executar_scan(tmp_path, paralelo=True, max_workers=4)

        codigos = {a.codigo for a in resultado.achados}
        assert {"VPS-001", "DE-002"}.issubset(codigos)


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

        executar_scan(tmp_path)  # nao deve levantar EntradaNaoRegistrada


class TestMissaoComMultiplosAchados:
    """Achado da validacao de FE-API: `_processar_entrada` so extraia
    `saida["achados"][0]`, descartando silenciosamente achados extras da
    MESMA Missao — uma rota ausente em analytics.py (a segunda do
    arquivo) desaparecia do resultado final mesmo o handler retornando
    corretamente as duas. Fixado para `_processar_entrada` retornar
    `list[AchadoScan]` completa."""

    def test_arquivo_com_duas_rotas_ausentes_produz_dois_achados(self, tmp_path: Path) -> None:
        from batman_os.capabilities.rules.feapi_loader import carregar_especificacoes_feapi

        (tmp_path / "api").mkdir()
        (tmp_path / "api" / "rotas.py").write_text(
            "@router.get('/primeira')\n"
            "def primeira():\n"
            "    pass\n"
            "@router.get('/segunda')\n"
            "def segunda():\n"
            "    pass\n",
            encoding="utf-8",
        )

        resultado = executar_scan(tmp_path, especificacoes=carregar_especificacoes_feapi())

        achados_feapi = [a for a in resultado.achados if a.codigo == "FE-API"]
        assert len(achados_feapi) == 2
        chaves = {a.arquivo for a in achados_feapi}
        assert chaves == {"api/rotas.py"}
        fingerprints = {a.fingerprint for a in achados_feapi}
        assert len(fingerprints) == 2

        assert resultado is not None


class TestPodaDeDiretoriosNoScan:
    """`DEFAULT_EXCLUDED_DIRS` (`descoberta_arquivos.py`) chegando até
    `executar_scan` — a poda em si já está coberta em unidade por
    `tests/cli/test_descoberta_arquivos.py`; aqui a garantia é o plumbing
    (parâmetros `excluir_dirs`/`usar_excludes_padrao` -> `escopo_de_
    exclusao_de_diretorios` -> `estatisticas_de_descoberta` no resultado)."""

    def test_estatisticas_de_descoberta_refletem_a_poda_por_padrao(self, tmp_path: Path) -> None:
        (tmp_path / "api").mkdir()
        (tmp_path / "api" / "a.py").write_text("x", encoding="utf-8")

        (tmp_path / ".venv" / "lib").mkdir(parents=True)
        for i in range(20):
            (tmp_path / ".venv" / "lib" / f"modulo_{i}.py").write_text("y", encoding="utf-8")

        resultado = executar_scan(tmp_path, especificacoes=carregar_lote_01())

        assert resultado.estatisticas_de_descoberta is not None
        assert resultado.estatisticas_de_descoberta.diretorios_podados >= 1
        # os 20 arquivos de .venv nao contam -- so o que sobra fora da poda
        assert resultado.estatisticas_de_descoberta.arquivos_enumerados == 1

    def test_achados_nao_mudam_com_lixo_podado_no_repo(self, tmp_path: Path) -> None:
        """Regressao de comportamento: a poda muda SO o que e enumerado
        para performance, nunca o conjunto de achados de um repo que ja
        passava sem `.venv`/`node_modules`."""
        (tmp_path / ".venv" / "lib").mkdir(parents=True)
        (tmp_path / ".venv" / "lib" / "x.py").write_text("SECRET_KEY = 'y'", encoding="utf-8")

        resultado = executar_scan(tmp_path, especificacoes=carregar_lote_01())

        codigos = {a.codigo for a in resultado.achados}
        assert codigos == {"VPS-001", "DE-002"}

    def test_excluir_dirs_customizado_soma_ao_default(self, tmp_path: Path) -> None:
        (tmp_path / "vendor").mkdir()
        (tmp_path / "vendor" / "a.py").write_text("x", encoding="utf-8")

        resultado = executar_scan(
            tmp_path,
            especificacoes=carregar_lote_01(),
            excluir_dirs=frozenset({"vendor"}),
        )

        assert resultado.estatisticas_de_descoberta is not None
        assert resultado.estatisticas_de_descoberta.arquivos_enumerados == 0
        assert resultado.estatisticas_de_descoberta.diretorios_podados == 1

    def test_no_default_excludes_desliga_a_poda_padrao(self, tmp_path: Path) -> None:
        (tmp_path / ".venv").mkdir()
        (tmp_path / ".venv" / "a.py").write_text("x", encoding="utf-8")

        resultado = executar_scan(
            tmp_path,
            especificacoes=carregar_lote_01(),
            usar_excludes_padrao=False,
        )

        assert resultado.estatisticas_de_descoberta is not None
        assert resultado.estatisticas_de_descoberta.diretorios_podados == 0
        assert resultado.estatisticas_de_descoberta.arquivos_enumerados == 1

    def test_no_default_excludes_combinado_com_exclude_e_100_por_cento_customizado(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / ".venv").mkdir()
        (tmp_path / ".venv" / "a.py").write_text("x", encoding="utf-8")
        (tmp_path / "vendor").mkdir()
        (tmp_path / "vendor" / "b.py").write_text("y", encoding="utf-8")

        resultado = executar_scan(
            tmp_path,
            especificacoes=carregar_lote_01(),
            usar_excludes_padrao=False,
            excluir_dirs=frozenset({"vendor"}),
        )

        assert resultado.estatisticas_de_descoberta is not None
        # .venv NAO e podado (default desligado); vendor e (customizado)
        assert resultado.estatisticas_de_descoberta.diretorios_podados == 1
        assert resultado.estatisticas_de_descoberta.arquivos_enumerados == 1

    def test_configuracao_de_exclusao_nao_vaza_entre_chamadas(self, tmp_path: Path) -> None:
        """A poda e configurada via um global module-level em
        `descoberta_arquivos.py` (`escopo_de_exclusao_de_diretorios`,
        usado internamente por `executar_scan`) -- precisa restaurar o
        default ao sair, senao uma chamada com `usar_excludes_padrao=False`
        vazaria "sem poda nenhuma" para a PROXIMA chamada no mesmo
        processo (comum em testes e em qualquer servico de longa
        duracao que chame `executar_scan` repetidamente)."""
        (tmp_path / ".venv").mkdir()
        (tmp_path / ".venv" / "a.py").write_text("x", encoding="utf-8")

        executar_scan(tmp_path, especificacoes=carregar_lote_01(), usar_excludes_padrao=False)
        resultado_depois = executar_scan(tmp_path, especificacoes=carregar_lote_01())

        assert resultado_depois.estatisticas_de_descoberta is not None
        assert resultado_depois.estatisticas_de_descoberta.arquivos_enumerados == 0
        assert resultado_depois.estatisticas_de_descoberta.diretorios_podados == 1


class TestLogDeVisibilidadeDaDescoberta:
    """`executar_scan` precisa logar, no inicio, quantos arquivos foram
    enumerados e quantos diretorios foram podados -- silencio aqui esconde
    regressao de performance (ex.: uma exclusao nova quebrada, ou um
    `scope_dirs` novo apontando pra raiz sem querer)."""

    def test_loga_contagem_de_arquivos_e_diretorios_podados(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        (tmp_path / ".venv").mkdir()
        (tmp_path / ".venv" / "a.py").write_text("x", encoding="utf-8")
        (tmp_path / "api").mkdir()
        (tmp_path / "api" / "b.py").write_text("y", encoding="utf-8")

        with caplog.at_level(logging.INFO, logger="batman_os.cli.scan_command"):
            executar_scan(tmp_path, especificacoes=carregar_lote_01())

        mensagens = [registro.message for registro in caplog.records]
        assert any(
            "arquivo(s) enumerados" in m and "diretorio(s) podado(s)" in m for m in mensagens
        )


def _achado_scan(
    codigo: str = "CTO-002",
    arquivo: str = "src/x.py",
    chave: str = "",
    severidade: str = "high",
    titulo: str = "timeout ausente",
    descricao: str = "chamada sem timeout",
) -> AchadoScan:
    return AchadoScan(
        codigo=codigo,
        agente="cto",
        severidade=severidade,
        categoria="reliability",
        titulo=titulo,
        descricao=descricao,
        causa="causa",
        remediacao="remediacao",
        arquivo=arquivo,
        chave=chave,
    )


class TestAchadosParaInbox:
    """Adaptador `AchadoScan` -> `AchadoInboxEntrada` (`achados_para_inbox`)
    — ponto 4 do pacote da capacidade Inbox (`governance/inbox.py`)."""

    def test_severidade_e_convertida_para_criticidade(self) -> None:
        resultado = ResultadoScan(achados=[_achado_scan(severidade="critical")])
        entradas = achados_para_inbox(resultado)

        assert entradas[0].severidade == Criticidade.CRITICAL

    def test_chave_dominio_usa_codigo_arquivo_e_chave(self) -> None:
        resultado = ResultadoScan(
            achados=[_achado_scan(codigo="FE-001", arquivo="src/a.ts", chave="nomeExportado")]
        )
        entradas = achados_para_inbox(resultado)

        assert entradas[0].chave_dominio == "FE-001|src/a.ts|nomeExportado"

    def test_dois_achados_da_mesma_regra_arquivo_com_chaves_distintas_nao_colidem(self) -> None:
        resultado = ResultadoScan(
            achados=[
                _achado_scan(codigo="FE-001", arquivo="src/a.ts", chave="foo"),
                _achado_scan(codigo="FE-001", arquivo="src/a.ts", chave="bar"),
            ]
        )
        entradas = achados_para_inbox(resultado)

        assert len({e.chave_dominio for e in entradas}) == 2

    def test_titulo_inclui_codigo_e_arquivo(self) -> None:
        resultado = ResultadoScan(
            achados=[_achado_scan(codigo="CTO-002", arquivo="src/x.py", titulo="timeout ausente")]
        )
        entradas = achados_para_inbox(resultado)

        assert entradas[0].titulo == "CTO-002 src/x.py: timeout ausente"

    def test_lista_vazia_produz_lista_vazia(self) -> None:
        assert achados_para_inbox(ResultadoScan(achados=[])) == []
