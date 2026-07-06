"""Testes da Skill "parsing TOML real de pyproject.toml" (Vol.IV Cap.17)."""

from __future__ import annotations

import json

import pytest

from batman_os.capabilities.capability_contract import certificar
from batman_os.capabilities.operator import ExecutionContext
from batman_os.capabilities.rules.toml_dependencias import (
    EntradaInvalida,
    avaliar_regra_dependencias,
    construir_implementacao,
)
from batman_os.foundation.types import MissionId, StepId, TenantId, agora
from batman_os.runtime.capability_engine import StatusCapability


def _contexto() -> ExecutionContext:
    return ExecutionContext(
        mission_id=MissionId("m-1"),
        tenant_id=TenantId("t-1"),
        step_id=StepId("s-1"),
        deadline=agora(),
    )


def _regra(aspecto: str, **overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "codigo": "TEST-001",
        "agente": "teste",
        "severidade": "high",
        "categoria": "cat",
        "titulo": "titulo",
        "causa": "causa",
        "remediacao": "remediacao",
        "aspecto": aspecto,
    }
    base.update(overrides)
    return base


def _entrada(regra: dict[str, object], payload: dict[str, object]) -> dict[str, object]:
    return {"caminho": "pyproject.toml", "conteudo": json.dumps(payload), "regra": regra}


_PYPROJECT_BASE = """
[project]
dependencies = ["fastapi>=0.100,<1.0", "requests>=2.0"]

[project.optional-dependencies]
dev = ["pytest>=8.0"]
"""


class TestImportNaoDeclarado:
    def test_dispara_quando_import_ausente_do_pyproject(self) -> None:
        entrada = _entrada(
            _regra("import_nao_declarado"),
            {
                "pyproject_texto": _PYPROJECT_BASE,
                "arquivos_tests": {"tests/test_a.py": "import pyarrow\n"},
                "arquivos_src": {},
            },
        )
        saida = avaliar_regra_dependencias(entrada, _contexto())
        assert len(saida["achados"]) == 1
        assert "pyarrow" in saida["achados"][0]["descricao"]

    def test_nao_dispara_quando_import_declarado(self) -> None:
        entrada = _entrada(
            _regra("import_nao_declarado"),
            {
                "pyproject_texto": _PYPROJECT_BASE,
                "arquivos_tests": {"tests/test_a.py": "import requests\n"},
                "arquivos_src": {},
            },
        )
        saida = avaliar_regra_dependencias(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_para_stdlib_ou_pacote_local(self) -> None:
        entrada = _entrada(
            _regra("import_nao_declarado"),
            {
                "pyproject_texto": _PYPROJECT_BASE,
                "arquivos_tests": {"tests/test_a.py": "import os\nimport src.foo\n"},
                "arquivos_src": {},
            },
        )
        saida = avaliar_regra_dependencias(entrada, _contexto())
        assert saida["achados"] == []

    def test_sem_pyproject_nao_dispara(self) -> None:
        entrada = _entrada(
            _regra("import_nao_declarado"),
            {"pyproject_texto": None, "arquivos_tests": {"tests/a.py": "import pyarrow\n"}},
        )
        saida = avaliar_regra_dependencias(entrada, _contexto())
        assert saida["achados"] == []


class TestParquetSemEngine:
    def test_dispara_quando_usa_parquet_sem_engine_declarado(self) -> None:
        entrada = _entrada(
            _regra("parquet_sem_engine"),
            {
                "pyproject_texto": _PYPROJECT_BASE,
                "arquivos_tests": {},
                "arquivos_src": {"src/x.py": "df.to_parquet('x.parquet')\n"},
            },
        )
        saida = avaliar_regra_dependencias(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_quando_pyarrow_declarado(self) -> None:
        pyproject = _PYPROJECT_BASE.replace(
            'dependencies = ["fastapi>=0.100,<1.0", "requests>=2.0"]',
            'dependencies = ["fastapi>=0.100,<1.0", "pyarrow>=14.0"]',
        )
        entrada = _entrada(
            _regra("parquet_sem_engine"),
            {
                "pyproject_texto": pyproject,
                "arquivos_tests": {},
                "arquivos_src": {"src/x.py": "df.to_parquet('x.parquet')\n"},
            },
        )
        saida = avaliar_regra_dependencias(entrada, _contexto())
        assert saida["achados"] == []


class TestSemLimiteSuperior:
    def test_dispara_para_dependencia_so_com_ge(self) -> None:
        entrada = _entrada(
            _regra("sem_limite_superior"),
            {
                "pyproject_texto": '[project]\ndependencies = ["requests>=2.0"]\n',
                "arquivos_tests": {},
                "arquivos_src": {},
            },
        )
        saida = avaliar_regra_dependencias(entrada, _contexto())
        assert len(saida["achados"]) == 1
        assert "requests" in saida["achados"][0]["descricao"]

    def test_nao_dispara_quando_tem_limite_superior(self) -> None:
        entrada = _entrada(
            _regra("sem_limite_superior"),
            {"pyproject_texto": _PYPROJECT_BASE, "arquivos_tests": {}, "arquivos_src": {}},
        )
        saida = avaliar_regra_dependencias(entrada, _contexto())
        # requests>=2.0 (sem limite) ainda deve disparar mesmo com fastapi tendo limite
        assert len(saida["achados"]) == 1

    def test_dispara_para_requirements_txt_tambem(self) -> None:
        entrada = _entrada(
            _regra("sem_limite_superior"),
            {
                "pyproject_texto": '[project]\ndependencies = ["fastapi>=0.100,<1.0"]\n',
                "requirements_texto": "numpy>=1.20\n",
                "arquivos_tests": {},
                "arquivos_src": {},
            },
        )
        saida = avaliar_regra_dependencias(entrada, _contexto())
        assert len(saida["achados"]) == 1
        assert "requirements.txt:numpy" in saida["achados"][0]["descricao"]


class TestDuplicadoProdDev:
    def test_dispara_quando_pacote_em_ambos_grupos(self) -> None:
        entrada = _entrada(
            _regra("duplicado_prod_dev"),
            {
                "pyproject_texto": (
                    '[project]\ndependencies = ["pytest>=8.0"]\n'
                    '[project.optional-dependencies]\ndev = ["pytest>=8.0"]\n'
                ),
                "arquivos_tests": {},
                "arquivos_src": {},
            },
        )
        saida = avaliar_regra_dependencias(entrada, _contexto())
        assert len(saida["achados"]) == 1
        assert "pytest" in saida["achados"][0]["descricao"]

    def test_nao_dispara_sem_sobreposicao(self) -> None:
        entrada = _entrada(
            _regra("duplicado_prod_dev"),
            {"pyproject_texto": _PYPROJECT_BASE, "arquivos_tests": {}, "arquivos_src": {}},
        )
        saida = avaliar_regra_dependencias(entrada, _contexto())
        assert saida["achados"] == []


class TestConteudoAusenteOuMalformado:
    def test_conteudo_none_retorna_vazio(self) -> None:
        entrada = {
            "caminho": "pyproject.toml",
            "conteudo": None,
            "regra": _regra("duplicado_prod_dev"),
        }
        saida = avaliar_regra_dependencias(entrada, _contexto())
        assert saida["achados"] == []

    def test_conteudo_nao_json_retorna_vazio(self) -> None:
        entrada = {
            "caminho": "pyproject.toml",
            "conteudo": "nao e json",
            "regra": _regra("duplicado_prod_dev"),
        }
        saida = avaliar_regra_dependencias(entrada, _contexto())
        assert saida["achados"] == []

    def test_toml_malformado_retorna_vazio(self) -> None:
        entrada = _entrada(
            _regra("duplicado_prod_dev"), {"pyproject_texto": "isto nao e = toml [[[ valido"}
        )
        saida = avaliar_regra_dependencias(entrada, _contexto())
        assert saida["achados"] == []


class TestEntradaInvalida:
    def test_levanta_excecao_sem_campo_regra(self) -> None:
        with pytest.raises(EntradaInvalida):
            avaliar_regra_dependencias({"caminho": "pyproject.toml"}, _contexto())


class TestCertificacao:
    def test_implementacao_real_passa_na_certificacao(self) -> None:
        impl = construir_implementacao()
        contexto = _contexto()
        entrada_idempotencia = _entrada(
            _regra("import_nao_declarado"),
            {
                "pyproject_texto": _PYPROJECT_BASE,
                "arquivos_tests": {"tests/a.py": "import pyarrow\n"},
                "arquivos_src": {},
            },
        )
        definicao_certificada = certificar(
            impl,
            entrada_para_teste_idempotencia=entrada_idempotencia,
            contexto_para_teste_idempotencia=contexto,
        )
        assert definicao_certificada.status == StatusCapability.ACTIVE
