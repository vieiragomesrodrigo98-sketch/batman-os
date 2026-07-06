"""Testes da Capability bespoke DE-003 (Vol.IV Cap.17)."""

from __future__ import annotations

import json

import pytest

from batman_os.capabilities.capability_contract import certificar
from batman_os.capabilities.operator import ExecutionContext
from batman_os.capabilities.rules.de003_coluna_sem_migration import (
    EntradaInvalida,
    avaliar_de003,
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


_INIT_DB_COBERTO = (
    "_NEW_FOO_COLUMNS = [('bar', 'TEXT')]\n\ndef f():\n    _migrate_table(x, 'foo')\n"
)
_INIT_DB_SEM_COBERTURA = "_NEW_OUTRA_COLUMNS = [('bar', 'TEXT')]\n"
_TABLES_SRC = "class Foo(Base):\n    __tablename__ = 'foo'\n"


def _entrada(
    payload: dict[str, object], regra: dict[str, object] | None = None
) -> dict[str, object]:
    return {
        "caminho": "api/database/tables.py",
        "conteudo": json.dumps(payload),
        "regra": regra or {},
    }


def _git_log_com_coluna_tardia(nome_coluna: str = "nova_coluna") -> str:
    return (
        "COMMIT:abc12345\n"
        "@@ -1,3 +1,4 @@ class Foo(\n"
        " class Foo(Base):\n"
        '     __tablename__ = "foo"\n'
        f"+    {nome_coluna}: Mapped[str] = mapped_column(nullable=True)\n"
    )


class TestDetecaoDeColunaTardia:
    def test_dispara_high_quando_tabela_coberta_por_migration(self) -> None:
        entrada = _entrada(
            {
                "aplica": True,
                "init_db_src": _INIT_DB_COBERTO,
                "tables_src": _TABLES_SRC,
                "git_log": _git_log_com_coluna_tardia(),
            }
        )
        saida = avaliar_de003(entrada, _contexto())
        assert len(saida["achados"]) == 1
        assert saida["achados"][0]["chave"] == "DE003-covered-missing"

    def test_dispara_med_quando_tabela_sem_cobertura(self) -> None:
        entrada = _entrada(
            {
                "aplica": True,
                "init_db_src": _INIT_DB_SEM_COBERTURA,
                "tables_src": _TABLES_SRC,
                "git_log": _git_log_com_coluna_tardia(),
            }
        )
        saida = avaliar_de003(entrada, _contexto())
        assert len(saida["achados"]) == 1
        assert saida["achados"][0]["chave"] == "DE003-uncovered-risk"

    def test_nao_dispara_quando_coluna_ja_registrada_em_migration_cols(self) -> None:
        entrada = _entrada(
            {
                "aplica": True,
                "init_db_src": "_NEW_FOO_COLUMNS = [('nova_coluna', 'TEXT')]\n"
                "def f():\n    _migrate_table(x, 'foo')\n",
                "tables_src": _TABLES_SRC,
                "git_log": _git_log_com_coluna_tardia(),
            }
        )
        saida = avaliar_de003(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_para_tabela_recem_criada(self) -> None:
        git_log = (
            "COMMIT:abc12345\n"
            "+class Foo(Base):\n"
            '+    __tablename__ = "foo"\n'
            "+    nova_coluna: Mapped[str] = mapped_column(nullable=True)\n"
        )
        entrada = _entrada(
            {
                "aplica": True,
                "init_db_src": _INIT_DB_SEM_COBERTURA,
                "tables_src": _TABLES_SRC,
                "git_log": git_log,
            }
        )
        saida = avaliar_de003(entrada, _contexto())
        assert saida["achados"] == []

    def test_coluna_removida_depois_nao_dispara(self) -> None:
        git_log = (
            _git_log_com_coluna_tardia()
            + "-    nova_coluna: Mapped[str] = mapped_column(nullable=True)\n"
        )
        entrada = _entrada(
            {
                "aplica": True,
                "init_db_src": _INIT_DB_SEM_COBERTURA,
                "tables_src": _TABLES_SRC,
                "git_log": git_log,
            }
        )
        saida = avaliar_de003(entrada, _contexto())
        assert saida["achados"] == []

    def test_coluna_sem_nullable_ou_default_nao_dispara(self) -> None:
        git_log = (
            "COMMIT:abc12345\n class Foo(Base):\n+    outra_coluna: Mapped[str] = mapped_column()\n"
        )
        entrada = _entrada(
            {
                "aplica": True,
                "init_db_src": _INIT_DB_SEM_COBERTURA,
                "tables_src": _TABLES_SRC,
                "git_log": git_log,
            }
        )
        saida = avaliar_de003(entrada, _contexto())
        assert saida["achados"] == []


class TestNaoAplica:
    def test_nao_aplica_retorna_vazio(self) -> None:
        entrada = _entrada({"aplica": False})
        saida = avaliar_de003(entrada, _contexto())
        assert saida["achados"] == []

    def test_git_log_vazio_retorna_vazio(self) -> None:
        entrada = _entrada(
            {
                "aplica": True,
                "init_db_src": _INIT_DB_COBERTO,
                "tables_src": _TABLES_SRC,
                "git_log": "",
            }
        )
        saida = avaliar_de003(entrada, _contexto())
        assert saida["achados"] == []

    def test_conteudo_none_retorna_vazio(self) -> None:
        entrada: dict[str, object] = {
            "caminho": "api/database/tables.py",
            "conteudo": None,
            "regra": {},
        }
        saida = avaliar_de003(entrada, _contexto())
        assert saida["achados"] == []

    def test_conteudo_nao_json_retorna_vazio(self) -> None:
        entrada = {"caminho": "api/database/tables.py", "conteudo": "nao e json", "regra": {}}
        saida = avaliar_de003(entrada, _contexto())
        assert saida["achados"] == []


class TestEntradaInvalida:
    def test_levanta_excecao_sem_campo_caminho(self) -> None:
        with pytest.raises(EntradaInvalida):
            avaliar_de003({"conteudo": "x"}, _contexto())


class TestCertificacao:
    def test_implementacao_real_passa_na_certificacao(self) -> None:
        impl = construir_implementacao()
        contexto = _contexto()
        entrada_idempotencia = _entrada(
            {
                "aplica": True,
                "init_db_src": _INIT_DB_COBERTO,
                "tables_src": _TABLES_SRC,
                "git_log": _git_log_com_coluna_tardia(),
            }
        )
        definicao_certificada = certificar(
            impl,
            entrada_para_teste_idempotencia=entrada_idempotencia,
            contexto_para_teste_idempotencia=contexto,
        )
        assert definicao_certificada.status == StatusCapability.ACTIVE
