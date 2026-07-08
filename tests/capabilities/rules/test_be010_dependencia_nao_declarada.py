"""Testes do handler bespoke BE-010 "dependência importada mas não
declarada" (`be010_dependencia_nao_declarada.py`)."""

from __future__ import annotations

import json

from batman_os.capabilities.operator import ExecutionContext
from batman_os.capabilities.rules.be010_dependencia_nao_declarada import avaliar_be010
from batman_os.foundation.types import MissionId, StepId, TenantId, agora


def _contexto() -> ExecutionContext:
    return ExecutionContext(
        mission_id=MissionId("m-1"),
        tenant_id=TenantId("t-1"),
        step_id=StepId("s-1"),
        deadline=agora(),
    )


def _regra() -> dict[str, object]:
    return {
        "codigo": "BE-010",
        "agente": "backend-engineer",
        "severidade": "low",
        "categoria": "imports",
        "titulo": "titulo",
        "causa": "causa",
        "remediacao": "remediacao",
    }


class TestDependenciaNaoDeclarada:
    def test_dispara_para_import_de_terceiro_nao_declarado(self) -> None:
        entrada = {
            "caminho": "pyproject.toml",
            "conteudo": json.dumps(
                {
                    "pyproject_texto": "[project]\ndependencies = ['fastapi']\n",
                    "local_modules": ["api", "src"],
                    "arquivos": {"api/x.py": "import bcrypt\n"},
                }
            ),
            "regra": _regra(),
        }
        saida = avaliar_be010(entrada, _contexto())
        assert len(saida["achados"]) == 1
        assert saida["achados"][0]["chave"] == "bcrypt"

    def test_nao_dispara_quando_import_esta_declarado(self) -> None:
        entrada = {
            "caminho": "pyproject.toml",
            "conteudo": json.dumps(
                {
                    "pyproject_texto": "[project]\ndependencies = ['bcrypt']\n",
                    "local_modules": ["api", "src"],
                    "arquivos": {"api/x.py": "import bcrypt\n"},
                }
            ),
            "regra": _regra(),
        }
        saida = avaliar_be010(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_para_stdlib(self) -> None:
        entrada = {
            "caminho": "pyproject.toml",
            "conteudo": json.dumps(
                {
                    "pyproject_texto": "[project]\ndependencies = []\n",
                    "local_modules": [],
                    "arquivos": {"api/x.py": "import json\nimport os\n"},
                }
            ),
            "regra": _regra(),
        }
        saida = avaliar_be010(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_para_modulo_local(self) -> None:
        entrada = {
            "caminho": "pyproject.toml",
            "conteudo": json.dumps(
                {
                    "pyproject_texto": "[project]\ndependencies = []\n",
                    "local_modules": ["meupacote"],
                    "arquivos": {"api/x.py": "import meupacote\n"},
                }
            ),
            "regra": _regra(),
        }
        saida = avaliar_be010(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_para_dependencia_transitiva_conhecida(self) -> None:
        entrada = {
            "caminho": "pyproject.toml",
            "conteudo": json.dumps(
                {
                    "pyproject_texto": "[project]\ndependencies = []\n",
                    "local_modules": [],
                    "arquivos": {"api/x.py": "import starlette\n"},
                }
            ),
            "regra": _regra(),
        }
        saida = avaliar_be010(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_sem_pyproject(self) -> None:
        entrada = {
            "caminho": "pyproject.toml",
            "conteudo": None,
            "regra": _regra(),
        }
        saida = avaliar_be010(entrada, _contexto())
        assert saida["achados"] == []

    def test_reporta_o_primeiro_arquivo_onde_o_import_aparece(self) -> None:
        entrada = {
            "caminho": "pyproject.toml",
            "conteudo": json.dumps(
                {
                    "pyproject_texto": "[project]\ndependencies = []\n",
                    "local_modules": [],
                    "arquivos": {
                        "api/a.py": "import bcrypt\n",
                        "api/b.py": "import bcrypt\n",
                    },
                }
            ),
            "regra": _regra(),
        }
        saida = avaliar_be010(entrada, _contexto())
        assert len(saida["achados"]) == 1
        assert saida["achados"][0]["arquivo"] == "api/a.py"

    def test_multiplos_imports_nao_declarados_produzem_multiplos_achados(self) -> None:
        entrada = {
            "caminho": "pyproject.toml",
            "conteudo": json.dumps(
                {
                    "pyproject_texto": "[project]\ndependencies = []\n",
                    "local_modules": [],
                    "arquivos": {"api/a.py": "import bcrypt\nimport requests\n"},
                }
            ),
            "regra": _regra(),
        }
        saida = avaliar_be010(entrada, _contexto())
        assert len(saida["achados"]) == 2
        chaves = {a["chave"] for a in saida["achados"]}
        assert chaves == {"bcrypt", "requests"}
