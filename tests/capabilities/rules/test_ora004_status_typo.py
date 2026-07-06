"""Testes da Capability bespoke ORA-004 (Vol.IV Cap.17)."""

from __future__ import annotations

import json

import pytest

from batman_os.capabilities.capability_contract import certificar
from batman_os.capabilities.operator import ExecutionContext
from batman_os.capabilities.rules.ora004_status_typo import (
    EntradaInvalida,
    avaliar_ora004,
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


def _entrada(arquivos: dict[str, str], enums_src: str | None = None) -> dict[str, object]:
    return {
        "caminho": "src",
        "conteudo": json.dumps({"arquivos": arquivos, "enums_src": enums_src}),
        "regra": {},
    }


class TestDeteccaoDeTypo:
    def test_dispara_para_literal_raro_a_1_char_do_dominante(self) -> None:
        arquivos = {
            "src/a.py": "\n".join([f"x = status == 'fechado'  # {i}" for i in range(4)]),
            "src/b.py": "y = status == 'fechada'",
        }
        entrada = _entrada(arquivos)
        saida = avaliar_ora004(entrada, _contexto())
        assert len(saida["achados"]) == 1
        assert saida["achados"][0]["chave"] == "fechada"

    def test_nao_dispara_sem_literal_dominante_o_bastante(self) -> None:
        # so 1 ocorrencia de cada - nenhum e 3x mais frequente que o outro
        arquivos = {"src/a.py": "x = status == 'fechado'\ny = status == 'fechada'"}
        entrada = _entrada(arquivos)
        saida = avaliar_ora004(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_para_literal_ja_no_enum_canonico(self) -> None:
        arquivos = {"src/a.py": "x = status == 'fechada'"}
        enums_src = "class StatusEnum:\n    FECHADA = 'fechada'\n"
        entrada = _entrada(arquivos, enums_src)
        saida = avaliar_ora004(entrada, _contexto())
        assert saida["achados"] == []

    def test_dispara_para_literal_raro_proximo_do_enum_canonico(self) -> None:
        arquivos = {"src/a.py": "x = status == 'fechada'"}
        enums_src = "class StatusEnum:\n    FECHADO = 'fechado'\n"
        entrada = _entrada(arquivos, enums_src)
        saida = avaliar_ora004(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_ignora_nome_que_nao_e_status(self) -> None:
        arquivos = {"src/a.py": "x = http_status == 'fechada'"}
        entrada = _entrada(arquivos)
        saida = avaliar_ora004(entrada, _contexto())
        assert saida["achados"] == []

    def test_sem_arquivos_retorna_vazio(self) -> None:
        entrada = _entrada({})
        saida = avaliar_ora004(entrada, _contexto())
        assert saida["achados"] == []


class TestConteudoAusenteOuMalformado:
    def test_conteudo_none_retorna_vazio(self) -> None:
        entrada: dict[str, object] = {"caminho": "src", "conteudo": None, "regra": {}}
        saida = avaliar_ora004(entrada, _contexto())
        assert saida["achados"] == []

    def test_conteudo_nao_json_retorna_vazio(self) -> None:
        entrada = {"caminho": "src", "conteudo": "nao e json", "regra": {}}
        saida = avaliar_ora004(entrada, _contexto())
        assert saida["achados"] == []


class TestEntradaInvalida:
    def test_levanta_excecao_sem_campo_caminho(self) -> None:
        with pytest.raises(EntradaInvalida):
            avaliar_ora004({"conteudo": "x"}, _contexto())


class TestCertificacao:
    def test_implementacao_real_passa_na_certificacao(self) -> None:
        impl = construir_implementacao()
        contexto = _contexto()
        arquivos = {
            "src/a.py": "\n".join([f"x = status == 'fechado'  # {i}" for i in range(4)]),
            "src/b.py": "y = status == 'fechada'",
        }
        entrada_idempotencia = _entrada(arquivos)
        definicao_certificada = certificar(
            impl,
            entrada_para_teste_idempotencia=entrada_idempotencia,
            contexto_para_teste_idempotencia=contexto,
        )
        assert definicao_certificada.status == StatusCapability.ACTIVE
