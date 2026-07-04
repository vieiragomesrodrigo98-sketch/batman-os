"""Testes de `cli/descoberta_arquivos.py` — único módulo desta migração que
toca disco de verdade (usa `tmp_path` para simular um repositório alvo)."""

from __future__ import annotations

from pathlib import Path

import pytest

from batman_os.capabilities.rules.regex_sobre_conteudo import RegraSpec
from batman_os.cli.descoberta_arquivos import (
    TipoDescobertaDesconhecido,
    arquivos_para_regra,
    entradas_para_regra,
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
