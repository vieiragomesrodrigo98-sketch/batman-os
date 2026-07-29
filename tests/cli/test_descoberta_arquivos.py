"""Testes de `cli/descoberta_arquivos.py` — único módulo desta migração que
toca disco de verdade (usa `tmp_path` para simular um repositório alvo)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from batman_os.capabilities.rules.regex_sobre_conteudo import RegraSpec
from batman_os.cli.descoberta_arquivos import (
    DEFAULT_EXCLUDED_DIRS,
    TipoDescobertaDesconhecido,
    arquivos_para_regra,
    calcular_estatisticas_de_descoberta,
    entradas_para_regra,
    escopo_de_exclusao_de_diretorios,
    exclusao_de_diretorios_atual,
)


def _regra(**overrides: object) -> RegraSpec:
    base: dict[str, object] = {
        "codigo": "TEST-001",
        "agente": "teste",
        "severidade": "high",
        "categoria": "cat",
        "titulo": "titulo",
        "causa": "causa",
        "remediacao": "remediacao",
        "modo": "presenca",
    }
    base.update(overrides)
    return RegraSpec.model_validate(base)


class TestArquivoFixo:
    def test_arquivo_presente_le_conteudo(self, tmp_path: Path) -> None:
        (tmp_path / ".env").write_text("X=1", encoding="utf-8")

        resultado = arquivos_para_regra(tmp_path, {"tipo": "arquivo_fixo", "caminho": ".env"})

        assert resultado == [(".env", "X=1")]

    def test_arquivo_ausente_retorna_none(self, tmp_path: Path) -> None:
        resultado = arquivos_para_regra(
            tmp_path, {"tipo": "arquivo_fixo", "caminho": ".env.production.example"}
        )

        assert resultado == [(".env.production.example", None)]

    def test_caminho_relatorio_sobrescreve_o_caminho_reportado(self, tmp_path: Path) -> None:
        """DE-002 do motor legado: checa 'alembic' no disco mas reporta o
        achado com path='.' (raiz do repo) — precisa bater fingerprint."""
        resultado = arquivos_para_regra(
            tmp_path,
            {"tipo": "arquivo_fixo", "caminho": "alembic", "caminho_relatorio": "."},
        )

        assert resultado == [(".", None)]

    def test_diretorio_presente_marca_sem_conteudo_textual(self, tmp_path: Path) -> None:
        (tmp_path / "alembic").mkdir()

        resultado = arquivos_para_regra(tmp_path, {"tipo": "arquivo_fixo", "caminho": "alembic"})

        assert resultado == [("alembic", "")]


class TestArvore:
    def test_encontra_arquivos_recursivamente_por_extensao(self, tmp_path: Path) -> None:
        (tmp_path / "api" / "sub").mkdir(parents=True)
        (tmp_path / "api" / "a.py").write_text("x", encoding="utf-8")
        (tmp_path / "api" / "sub" / "b.py").write_text("y", encoding="utf-8")
        (tmp_path / "api" / "c.txt").write_text("z", encoding="utf-8")

        resultado = arquivos_para_regra(
            tmp_path, {"tipo": "arvore", "scope_dirs": ["api"], "extensoes": [".py"]}
        )

        assert {c for c, _ in resultado} == {"api/a.py", "api/sub/b.py"}

    def test_scope_dir_inexistente_e_ignorado_sem_erro(self, tmp_path: Path) -> None:
        resultado = arquivos_para_regra(
            tmp_path, {"tipo": "arvore", "scope_dirs": ["nao-existe"], "extensoes": [".py"]}
        )

        assert resultado == []

    def test_excluir_caminho_prefixo(self, tmp_path: Path) -> None:
        (tmp_path / "api" / "tests").mkdir(parents=True)
        (tmp_path / "api" / "tests" / "a.py").write_text("x", encoding="utf-8")
        (tmp_path / "api" / "b.py").write_text("y", encoding="utf-8")

        resultado = arquivos_para_regra(
            tmp_path,
            {
                "tipo": "arvore",
                "scope_dirs": ["api"],
                "extensoes": [".py"],
                "excluir_caminho_prefixo": ["api/tests/"],
            },
        )

        assert {c for c, _ in resultado} == {"api/b.py"}

    def test_excluir_nome_prefixo(self, tmp_path: Path) -> None:
        (tmp_path / "api").mkdir()
        (tmp_path / "api" / "test_a.py").write_text("x", encoding="utf-8")
        (tmp_path / "api" / "b.py").write_text("y", encoding="utf-8")

        resultado = arquivos_para_regra(
            tmp_path,
            {
                "tipo": "arvore",
                "scope_dirs": ["api"],
                "extensoes": [".py"],
                "excluir_nome_prefixo": ["test_"],
            },
        )

        assert {c for c, _ in resultado} == {"api/b.py"}

    def test_excluir_caminho_contem_lower_case_insensitive(self, tmp_path: Path) -> None:
        (tmp_path / "api").mkdir()
        (tmp_path / "api" / "TestUtil.py").write_text("x", encoding="utf-8")
        (tmp_path / "api" / "b.py").write_text("y", encoding="utf-8")

        resultado = arquivos_para_regra(
            tmp_path,
            {
                "tipo": "arvore",
                "scope_dirs": ["api"],
                "extensoes": [".py"],
                "excluir_caminho_contem_lower": ["test"],
            },
        )

        assert {c for c, _ in resultado} == {"api/b.py"}


class TestGlob:
    def test_padroes_root_relativos(self, tmp_path: Path) -> None:
        (tmp_path / "nginx").mkdir()
        (tmp_path / "nginx.conf").write_text("a", encoding="utf-8")
        (tmp_path / "nginx" / "site.conf").write_text("b", encoding="utf-8")

        resultado = arquivos_para_regra(
            tmp_path, {"tipo": "glob", "padroes": ["nginx.conf", "nginx/*.conf"]}
        )

        assert {c for c, _ in resultado} == {"nginx.conf", "nginx/site.conf"}

    def test_padrao_recursivo_com_exclusao(self, tmp_path: Path) -> None:
        (tmp_path / ".venv").mkdir()
        (tmp_path / ".venv" / "Dockerfile").write_text("dentro do venv", encoding="utf-8")
        (tmp_path / "Dockerfile").write_text("principal", encoding="utf-8")
        (tmp_path / "services").mkdir()
        (tmp_path / "services" / "Dockerfile.api").write_text("servico", encoding="utf-8")

        resultado = arquivos_para_regra(
            tmp_path,
            {
                "tipo": "glob",
                "padrao_recursivo": "Dockerfile*",
                "excluir_caminho_contem": [".venv"],
            },
        )

        assert {c for c, _ in resultado} == {"Dockerfile", "services/Dockerfile.api"}

    def test_tipo_desconhecido_levanta_excecao(self, tmp_path: Path) -> None:
        with pytest.raises(TipoDescobertaDesconhecido):
            arquivos_para_regra(tmp_path, {"tipo": "inexistente"})


class TestCondicoesAdicionais:
    def test_arquivo_fixo_com_vazio_se_ausente(self, tmp_path: Path) -> None:
        (tmp_path / ".env").write_text("X=1", encoding="utf-8")

        entradas = entradas_para_regra(
            tmp_path,
            _regra(codigo="DEVOPS-003", modo="arquivo-presente"),
            {
                "tipo": "arquivo_fixo",
                "caminho": ".env",
                "condicoes_adicionais": [
                    {
                        "tipo": "arquivo_fixo",
                        "caminho": ".gitignore",
                        "checar": "ausencia",
                        "pattern": r"\.env",
                        "vazio_se_ausente": True,
                    }
                ],
            },
        )

        assert len(entradas) == 1
        assert entradas[0].condicoes_adicionais[0].conteudo == ""

    def test_glob_existe_encontra_dockerfile(self, tmp_path: Path) -> None:
        (tmp_path / "Dockerfile").write_text("x", encoding="utf-8")

        entradas = entradas_para_regra(
            tmp_path,
            _regra(codigo="CLOUD-007", modo="arquivo-ausente"),
            {
                "tipo": "arquivo_fixo",
                "caminho": ".dockerignore",
                "condicoes_adicionais": [
                    {
                        "tipo": "glob_existe",
                        "padrao_recursivo": "Dockerfile*",
                        "excluir_caminho_contem": [".venv"],
                        "checar": "arquivo-presente",
                    }
                ],
            },
        )

        assert entradas[0].condicoes_adicionais[0].conteudo == "existe"

    def test_glob_existe_nao_encontra_nada(self, tmp_path: Path) -> None:
        entradas = entradas_para_regra(
            tmp_path,
            _regra(codigo="CLOUD-007", modo="arquivo-ausente"),
            {
                "tipo": "arquivo_fixo",
                "caminho": ".dockerignore",
                "condicoes_adicionais": [
                    {
                        "tipo": "glob_existe",
                        "padrao_recursivo": "Dockerfile*",
                        "checar": "arquivo-presente",
                    }
                ],
            },
        )

        assert entradas[0].condicoes_adicionais[0].conteudo is None


class TestEntradasParaRegra:
    def test_monta_uma_entrada_por_arquivo_encontrado(self, tmp_path: Path) -> None:
        (tmp_path / "api").mkdir()
        (tmp_path / "api" / "a.py").write_text("SECRET_KEY = 'x'", encoding="utf-8")
        (tmp_path / "api" / "b.py").write_text("nada", encoding="utf-8")

        entradas = entradas_para_regra(
            tmp_path,
            _regra(pattern="SECRET_KEY"),
            {"tipo": "arvore", "scope_dirs": ["api"], "extensoes": [".py"]},
        )

        assert {e.caminho for e in entradas} == {"api/a.py", "api/b.py"}
        assert all(e.regra.codigo == "TEST-001" for e in entradas)


class TestPodaDeDiretoriosPorPadrao:
    """`DEFAULT_EXCLUDED_DIRS` — poda a DESCIDA em `.venv`/`node_modules`/
    etc por padrão em QUALQUER travessia recursiva, mesmo sem o autor da
    regra configurar `excluir_caminho_contem` manualmente (achado real:
    `batman scan --root <repo>` enumerava a árvore inteira porque 3 specs
    de `lote_03` usam `scope_dirs: ["."]` — ver `DEFAULT_EXCLUDED_DIRS`)."""

    def test_arvore_com_scope_raiz_nao_desce_em_venv_nem_node_modules(self, tmp_path: Path) -> None:
        (tmp_path / "api").mkdir()
        (tmp_path / "api" / "a.py").write_text("x", encoding="utf-8")

        (tmp_path / ".venv" / "lib").mkdir(parents=True)
        (tmp_path / ".venv" / "lib" / "pacote.py").write_text("y", encoding="utf-8")

        (tmp_path / "node_modules" / "pkg").mkdir(parents=True)
        (tmp_path / "node_modules" / "pkg" / "indice.py").write_text("z", encoding="utf-8")

        resultado = arquivos_para_regra(
            tmp_path, {"tipo": "arvore", "scope_dirs": ["."], "extensoes": [".py"]}
        )

        assert {c for c, _ in resultado} == {"api/a.py"}

    def test_glob_padrao_recursivo_nao_desce_em_venv_sem_precisar_de_exclusao_manual(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "Dockerfile").write_text("principal", encoding="utf-8")
        (tmp_path / ".venv").mkdir()
        (tmp_path / ".venv" / "Dockerfile").write_text("dentro do venv", encoding="utf-8")

        # Sem `excluir_caminho_contem` (o mecanismo antigo, opt-in por spec)
        # — a poda por default precisa bastar sozinha.
        resultado = arquivos_para_regra(
            tmp_path, {"tipo": "glob", "padrao_recursivo": "Dockerfile*"}
        )

        assert {c for c, _ in resultado} == {"Dockerfile"}

    def test_glob_existe_ignora_arquivo_dentro_de_node_modules(self, tmp_path: Path) -> None:
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "Dockerfile").write_text("x", encoding="utf-8")

        entradas = entradas_para_regra(
            tmp_path,
            _regra(codigo="CLOUD-007", modo="arquivo-ausente"),
            {
                "tipo": "arquivo_fixo",
                "caminho": ".dockerignore",
                "condicoes_adicionais": [
                    {
                        "tipo": "glob_existe",
                        "padrao_recursivo": "Dockerfile*",
                        "checar": "arquivo-presente",
                    }
                ],
            },
        )

        assert entradas[0].condicoes_adicionais[0].conteudo is None

    def test_rev005_nao_desce_em_venv(self, tmp_path: Path) -> None:
        # `_resultado_rev005` só considera arquivos com >= 50 linhas.
        conteudo_longo = "linha\n" * 60

        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "a.py").write_text(conteudo_longo, encoding="utf-8")
        (tmp_path / ".venv" / "lib").mkdir(parents=True)
        (tmp_path / ".venv" / "lib" / "b.py").write_text(conteudo_longo, encoding="utf-8")

        resultado = arquivos_para_regra(
            tmp_path,
            {"tipo": "rev005", "scope_dirs": ["."], "max_files": 20},
        )

        payload = json.loads(resultado[0][1] or "{}")
        # `_resultado_rev005` reporta via `str(Path.relative_to())` puro
        # (sem normalizar para posix como `_rel_posix`) -- normaliza aqui
        # só para a asserção ser estável entre SO.
        caminhos = {chave.replace("\\", "/") for chave in payload["arquivos"]}
        assert caminhos == {"src/a.py"}


class TestExclusaoDeDiretoriosConfiguravel:
    """`escopo_de_exclusao_de_diretorios`/`definir_exclusao_de_diretorios` —
    mecanismo que a CLI (`batman scan --exclude NOME` / `--no-default-
    excludes`) usa por trás para configurar a poda; testado aqui
    diretamente (a cadeia completa CLI -> `executar_scan` está em
    `tests/cli/test_batman_cli.py`/`test_scan_command.py`)."""

    def test_exclude_customizado_soma_aos_defaults(self, tmp_path: Path) -> None:
        (tmp_path / "vendor").mkdir()
        (tmp_path / "vendor" / "a.py").write_text("x", encoding="utf-8")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "b.py").write_text("y", encoding="utf-8")

        with escopo_de_exclusao_de_diretorios(DEFAULT_EXCLUDED_DIRS | {"vendor"}):
            resultado = arquivos_para_regra(
                tmp_path, {"tipo": "arvore", "scope_dirs": ["."], "extensoes": [".py"]}
            )

        assert {c for c, _ in resultado} == {"src/b.py"}

    def test_no_default_excludes_restaura_a_travessia_completa(self, tmp_path: Path) -> None:
        (tmp_path / ".venv").mkdir()
        (tmp_path / ".venv" / "a.py").write_text("x", encoding="utf-8")

        with escopo_de_exclusao_de_diretorios(frozenset()):
            resultado = arquivos_para_regra(
                tmp_path, {"tipo": "arvore", "scope_dirs": ["."], "extensoes": [".py"]}
            )

        assert {c for c, _ in resultado} == {".venv/a.py"}

    def test_default_e_restaurado_ao_sair_do_escopo(self, tmp_path: Path) -> None:
        assert exclusao_de_diretorios_atual() == DEFAULT_EXCLUDED_DIRS

        with escopo_de_exclusao_de_diretorios(frozenset()):
            assert exclusao_de_diretorios_atual() == frozenset()

        assert exclusao_de_diretorios_atual() == DEFAULT_EXCLUDED_DIRS

    def test_default_e_restaurado_mesmo_com_excecao_dentro_do_escopo(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            with escopo_de_exclusao_de_diretorios(frozenset()):
                raise ValueError("erro dentro do escopo")

        assert exclusao_de_diretorios_atual() == DEFAULT_EXCLUDED_DIRS


class TestEstatisticasDeDescoberta:
    """`calcular_estatisticas_de_descoberta` — visibilidade obrigatória no
    início do scan (`scan_command.py::executar_scan`): quantos arquivos
    sobrevivem à poda e quantos diretórios foram podados."""

    def test_conta_arquivos_e_diretorios_podados(self, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "a.py").write_text("x", encoding="utf-8")
        (tmp_path / "src" / "b.py").write_text("y", encoding="utf-8")

        (tmp_path / ".venv" / "lib").mkdir(parents=True)
        (tmp_path / ".venv" / "lib" / "muitos.py").write_text("z", encoding="utf-8")

        (tmp_path / "node_modules" / "pkg").mkdir(parents=True)
        (tmp_path / "node_modules" / "pkg" / "indice.js").write_text("w", encoding="utf-8")

        estatisticas = calcular_estatisticas_de_descoberta(tmp_path, DEFAULT_EXCLUDED_DIRS)

        assert estatisticas.arquivos_enumerados == 2  # só os dois de src/
        assert estatisticas.diretorios_podados == 2  # .venv e node_modules

    def test_padrao_glob_por_segmento_poda_egg_info(self, tmp_path: Path) -> None:
        (tmp_path / "pacote.egg-info").mkdir()
        (tmp_path / "pacote.egg-info" / "PKG-INFO").write_text("x", encoding="utf-8")

        estatisticas = calcular_estatisticas_de_descoberta(tmp_path, DEFAULT_EXCLUDED_DIRS)

        assert estatisticas.diretorios_podados == 1
        assert estatisticas.arquivos_enumerados == 0

    def test_sem_exclusao_conta_tudo(self, tmp_path: Path) -> None:
        (tmp_path / ".venv").mkdir()
        (tmp_path / ".venv" / "a.py").write_text("x", encoding="utf-8")

        estatisticas = calcular_estatisticas_de_descoberta(tmp_path, frozenset())

        assert estatisticas.arquivos_enumerados == 1
        assert estatisticas.diretorios_podados == 0

    def test_root_inexistente_nao_crasha(self, tmp_path: Path) -> None:
        estatisticas = calcular_estatisticas_de_descoberta(tmp_path / "nao-existe")

        assert estatisticas.arquivos_enumerados == 0
        assert estatisticas.diretorios_podados == 0
