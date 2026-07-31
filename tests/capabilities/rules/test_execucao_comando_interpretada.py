"""Testes da Skill "executar comando externo, timeout, venv-aware" (Vol.IV Cap.17)."""

from __future__ import annotations

import json

import pytest

from batman_os.capabilities.capability_contract import certificar
from batman_os.capabilities.operator import ExecutionContext
from batman_os.capabilities.rules.execucao_comando_interpretada import (
    EntradaInvalida,
    avaliar_regra_execucao_comando,
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


def _regra(interpretacao: str, **overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "codigo": "TEST-001",
        "agente": "teste",
        "severidade": "high",
        "categoria": "cat",
        "titulo": "titulo",
        "causa": "causa",
        "remediacao": "remediacao",
        "interpretacao": interpretacao,
    }
    base.update(overrides)
    return base


def _entrada(
    regra: dict[str, object], resultado: dict[str, object], caminho: str = "x"
) -> dict[str, object]:
    return {"caminho": caminho, "conteudo": json.dumps(resultado), "regra": regra}


class TestPytestFalhou:
    def test_dispara_quando_ha_falhas(self) -> None:
        entrada = _entrada(
            _regra("pytest_falhou"),
            {
                "returncode": 1,
                "stdout": "FAILED tests/test_a.py::test_x\n1 failed, 2 passed",
                "stderr": "",
                "dir_requerido_existe": True,
            },
        )
        saida = avaliar_regra_execucao_comando(entrada, _contexto())
        assert len(saida["achados"]) == 1
        assert "test_a.py::test_x" in saida["achados"][0]["chave"]

    def test_nao_dispara_quando_dir_ausente(self) -> None:
        entrada = _entrada(
            _regra("pytest_falhou"),
            {"returncode": 1, "stdout": "", "stderr": "", "dir_requerido_existe": False},
        )
        saida = avaliar_regra_execucao_comando(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_quando_returncode_zero(self) -> None:
        entrada = _entrada(
            _regra("pytest_falhou"),
            {"returncode": 0, "stdout": "", "stderr": "", "dir_requerido_existe": True},
        )
        saida = avaliar_regra_execucao_comando(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_quando_returncode_cinco(self) -> None:
        # rc=5 (nada coletado) e tratado por pytest_sem_testes, nao aqui
        entrada = _entrada(
            _regra("pytest_falhou"),
            {"returncode": 5, "stdout": "", "stderr": "", "dir_requerido_existe": True},
        )
        saida = avaliar_regra_execucao_comando(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_quando_pytest_nao_encontrado(self) -> None:
        entrada = _entrada(
            _regra("pytest_falhou"),
            {"returncode": -1, "stdout": "", "stderr": "", "dir_requerido_existe": True},
        )
        saida = avaliar_regra_execucao_comando(entrada, _contexto())
        assert saida["achados"] == []

    def test_timeout_do_scanner_vira_achado_low_nunca_high(self) -> None:
        """Recalibração QA-RUN-001 (lição da triagem dos 44 HIGH do
        radar-preditivo, 2026-07-30): timeout do pytest DENTRO do teto do
        scanner (`-2`, sentinela de `_rodar_subprocess_cacheado`) não é
        "suite quebrada" — é o scanner que não esperou o bastante. A suite
        real do radar leva ~25min e passa com milhares de testes verdes;
        o spec de QA-RUN-001 declara severidade "high", mas o achado de
        timeout tem que SEMPRE sair "low", nunca herdar a severidade do
        spec (prova de fogo da recalibração)."""
        entrada = _entrada(
            _regra("pytest_falhou", severidade="high"),
            {
                "returncode": -2,
                "stdout": "",
                "stderr": "comando excedeu timeout de 120s",
                "dir_requerido_existe": True,
            },
        )
        saida = avaliar_regra_execucao_comando(entrada, _contexto())
        assert len(saida["achados"]) == 1
        achado = saida["achados"][0]
        assert achado["severidade"] == "low"
        assert achado["chave"] == "timeout-do-scanner"
        assert "quebrada" not in achado["descricao"]

    def test_timeout_nao_e_confundido_com_falha_real(self) -> None:
        """FP oposto: um rc real de falha (não -2) continua HIGH — a
        recalibração só reclassifica o SENTINELA de timeout, não afrouxa
        a detecção de falha real."""
        entrada = _entrada(
            _regra("pytest_falhou", severidade="high"),
            {
                "returncode": 1,
                "stdout": "FAILED tests/test_a.py::test_x\n1 failed, 2 passed",
                "stderr": "",
                "dir_requerido_existe": True,
            },
        )
        saida = avaliar_regra_execucao_comando(entrada, _contexto())
        assert len(saida["achados"]) == 1
        assert saida["achados"][0]["severidade"] == "high"


class TestPytestSemTestes:
    def test_dispara_quando_dir_ausente(self) -> None:
        entrada = _entrada(
            _regra("pytest_sem_testes"),
            {"returncode": None, "stdout": "", "stderr": "", "dir_requerido_existe": False},
        )
        saida = avaliar_regra_execucao_comando(entrada, _contexto())
        assert len(saida["achados"]) == 1
        assert saida["achados"][0]["chave"] == "no-tests-dir"

    def test_dispara_quando_sem_arquivos_de_teste(self) -> None:
        entrada = _entrada(
            _regra("pytest_sem_testes"),
            {
                "returncode": 5,
                "stdout": "",
                "stderr": "",
                "dir_requerido_existe": True,
                "arquivos_teste_encontrados": [],
            },
        )
        saida = avaliar_regra_execucao_comando(entrada, _contexto())
        assert len(saida["achados"]) == 1
        assert saida["achados"][0]["chave"] == "no-test-files"

    def test_dispara_quando_nada_coletado(self) -> None:
        entrada = _entrada(
            _regra("pytest_sem_testes"),
            {
                "returncode": 5,
                "stdout": "",
                "stderr": "",
                "dir_requerido_existe": True,
                "arquivos_teste_encontrados": ["test_a.py"],
            },
        )
        saida = avaliar_regra_execucao_comando(entrada, _contexto())
        assert len(saida["achados"]) == 1
        assert saida["achados"][0]["chave"] == "pytest-nothing-collected"

    def test_nao_dispara_quando_testes_coletados_normalmente(self) -> None:
        entrada = _entrada(
            _regra("pytest_sem_testes"),
            {
                "returncode": 0,
                "stdout": "",
                "stderr": "",
                "dir_requerido_existe": True,
                "arquivos_teste_encontrados": ["test_a.py"],
            },
        )
        saida = avaliar_regra_execucao_comando(entrada, _contexto())
        assert saida["achados"] == []


class TestPytestIndisponivel:
    def test_dispara_quando_nao_encontrado(self) -> None:
        entrada = _entrada(
            _regra("pytest_indisponivel"), {"returncode": -1, "stdout": "", "stderr": "nao achado"}
        )
        saida = avaliar_regra_execucao_comando(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_quando_disponivel(self) -> None:
        entrada = _entrada(
            _regra("pytest_indisponivel"), {"returncode": 0, "stdout": "", "stderr": ""}
        )
        saida = avaliar_regra_execucao_comando(entrada, _contexto())
        assert saida["achados"] == []


class TestRuffNomeIndefinido:
    def test_agrupa_por_arquivo_e_simbolo(self) -> None:
        itens = [
            {
                "code": "F821",
                "filename": "a.py",
                "message": "Undefined name `foo`",
                "location": {"row": 10},
            },
            {
                "code": "F821",
                "filename": "a.py",
                "message": "Undefined name `foo`",
                "location": {"row": 20},
            },
            {"code": "F401", "filename": "a.py", "message": "unused `bar`", "location": {"row": 1}},
        ]
        entrada = _entrada(
            _regra("ruff_nome_indefinido"),
            {"returncode": 0, "stdout": json.dumps(itens), "stderr": ""},
        )
        saida = avaliar_regra_execucao_comando(entrada, _contexto())
        assert len(saida["achados"]) == 1
        assert saida["achados"][0]["chave"] == "foo"

    def test_nao_dispara_quando_rc_nao_zero(self) -> None:
        entrada = _entrada(
            _regra("ruff_nome_indefinido"), {"returncode": 2, "stdout": "", "stderr": "erro"}
        )
        saida = avaliar_regra_execucao_comando(entrada, _contexto())
        assert saida["achados"] == []


class TestRuffImportNaoUsado:
    def test_agrupa_por_arquivo(self) -> None:
        itens = [
            {"code": "F401", "filename": "a.py", "message": "unused `os`", "location": {"row": 1}},
            {"code": "F401", "filename": "a.py", "message": "unused `sys`", "location": {"row": 2}},
        ]
        entrada = _entrada(
            _regra("ruff_import_nao_usado"),
            {"returncode": 0, "stdout": json.dumps(itens), "stderr": ""},
        )
        saida = avaliar_regra_execucao_comando(entrada, _contexto())
        assert len(saida["achados"]) == 1
        assert "2 import" in saida["achados"][0]["descricao"]


class TestRuffIndisponivel:
    def test_dispara_quando_rc_nao_zero(self) -> None:
        entrada = _entrada(
            _regra("ruff_indisponivel"), {"returncode": 2, "stdout": "", "stderr": "timeout"}
        )
        saida = avaliar_regra_execucao_comando(entrada, _contexto())
        assert len(saida["achados"]) == 1
        assert saida["achados"][0]["chave"] == "ruff-error"

    def test_nao_dispara_quando_rc_zero(self) -> None:
        entrada = _entrada(
            _regra("ruff_indisponivel"), {"returncode": 0, "stdout": "[]", "stderr": ""}
        )
        saida = avaliar_regra_execucao_comando(entrada, _contexto())
        assert saida["achados"] == []

    def test_timeout_do_scanner_vira_achado_low_nao_ruff_falhou(self) -> None:
        """Mesmo bug do QA-RUN-001, achado durante a recalibração: timeout
        do ruff (-2) caía no mesmo ramo de 'ruff falhou' (rc != 0) — agora
        vira o mesmo achado próprio de timeout, sempre low."""
        entrada = _entrada(
            _regra("ruff_indisponivel", severidade="high"),
            {"returncode": -2, "stdout": "", "stderr": "comando excedeu timeout de 60s"},
        )
        saida = avaliar_regra_execucao_comando(entrada, _contexto())
        assert len(saida["achados"]) == 1
        assert saida["achados"][0]["severidade"] == "low"
        assert saida["achados"][0]["chave"] == "timeout-do-scanner"
        assert "ruff-error" != saida["achados"][0]["chave"]


class TestConteudoAusenteOuMalformado:
    def test_conteudo_none_retorna_vazio(self) -> None:
        entrada = {"caminho": "x", "conteudo": None, "regra": _regra("ruff_indisponivel")}
        saida = avaliar_regra_execucao_comando(entrada, _contexto())
        assert saida["achados"] == []

    def test_conteudo_nao_json_retorna_vazio(self) -> None:
        entrada = {"caminho": "x", "conteudo": "nao e json", "regra": _regra("ruff_indisponivel")}
        saida = avaliar_regra_execucao_comando(entrada, _contexto())
        assert saida["achados"] == []


class TestEntradaInvalida:
    def test_levanta_excecao_sem_campo_regra(self) -> None:
        with pytest.raises(EntradaInvalida):
            avaliar_regra_execucao_comando({"caminho": "x"}, _contexto())


class TestCertificacao:
    def test_implementacao_real_passa_na_certificacao(self) -> None:
        impl = construir_implementacao()
        contexto = _contexto()
        entrada_idempotencia = _entrada(
            _regra("pytest_falhou"),
            {"returncode": 1, "stdout": "1 failed", "stderr": "", "dir_requerido_existe": True},
        )
        definicao_certificada = certificar(
            impl,
            entrada_para_teste_idempotencia=entrada_idempotencia,
            contexto_para_teste_idempotencia=contexto,
        )
        assert definicao_certificada.status == StatusCapability.ACTIVE
