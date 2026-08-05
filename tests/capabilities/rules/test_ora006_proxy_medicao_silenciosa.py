"""Testes da Capability bespoke ORA-006 (Vol.IV Cap.17)."""

from __future__ import annotations

from typing import Any

import pytest

from batman_os.capabilities.capability_contract import certificar
from batman_os.capabilities.operator import ExecutionContext
from batman_os.capabilities.rules.ora006_proxy_medicao_silenciosa import (
    EntradaInvalida,
    avaliar_ora006,
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


def _avaliar(conteudo: str | None) -> Any:
    entrada: dict[str, object] = {"caminho": "src/x.py", "conteudo": conteudo, "regra": {}}
    return avaliar_ora006(entrada, _contexto())


class TestDisparo:
    def test_dispara_para_proxy_calculado_apos_is_none(self) -> None:
        saida = _avaliar(
            "def build_outcome(entry, tgt):\n"
            "    mfe = measure_excursions(entry)\n"
            "    if mfe is None:\n"
            "        mfe = tgt - entry\n"
            "    return mfe\n"
        )
        assert len(saida["achados"]) == 1
        assert saida["achados"][0]["chave"] == "silent-measurement-proxy"
        assert "linha(s) 4" in saida["achados"][0]["descricao"]

    def test_dispara_para_guarda_invertida_com_proxy_no_else(self) -> None:
        saida = _avaliar(
            "def f(a, b):\n"
            "    x = medir(a)\n"
            "    if x is not None:\n"
            "        usar(x)\n"
            "    else:\n"
            "        x = a * b\n"
            "    return x\n"
        )
        assert len(saida["achados"]) == 1

    def test_dispara_para_guarda_if_not_x(self) -> None:
        saida = _avaliar(
            "def f(a, b):\n    x = medir(a)\n    if not x:\n        x = max(a, b)\n    return x\n"
        )
        assert len(saida["achados"]) == 1

    def test_dispara_para_return_de_valor_fabricado(self) -> None:
        saida = _avaliar(
            "def f(a, b):\n"
            "    x = medir(a)\n"
            "    if x is None:\n"
            "        return a - b\n"
            "    return x\n"
        )
        assert len(saida["achados"]) == 1

    def test_nao_dispara_quando_o_fallback_loga(self) -> None:
        saida = _avaliar(
            "def f(a, b):\n"
            "    x = medir(a)\n"
            "    if x is None:\n"
            "        logger.warning('medicao falhou, usando proxy')\n"
            "        x = a - b\n"
            "    return x\n"
        )
        assert saida["achados"] == []

    def test_nao_dispara_quando_o_fallback_levanta(self) -> None:
        saida = _avaliar(
            "def f(a):\n"
            "    x = medir(a)\n"
            "    if x is None:\n"
            "        raise ValueError('sem medida')\n"
            "    return x\n"
        )
        assert saida["achados"] == []

    def test_nao_dispara_para_constante_sentinela(self) -> None:
        # `x = 0` é sentinela visível na revisão, não proxy calculado.
        saida = _avaliar(
            "def f(a):\n    x = medir(a)\n    if x is None:\n        x = 0\n    return x\n"
        )
        assert saida["achados"] == []

    def test_nao_dispara_para_lookup_de_orm(self) -> None:
        # "não achei no banco" != "não consegui medir" — get-or-create é
        # padrão legítimo.
        saida = _avaliar(
            "def f(db, a):\n"
            "    row = db.query(a).first()\n"
            "    if row is None:\n"
            "        row = criar_default(a)\n"
            "    return row\n"
        )
        assert saida["achados"] == []

    def test_nao_dispara_quando_origem_e_construtor(self) -> None:
        saida = _avaliar(
            "def f(a):\n"
            "    obj = Outcome(a)\n"
            "    if obj is None:\n"
            "        obj = fabricar(a)\n"
            "    return obj\n"
        )
        assert saida["achados"] == []

    def test_nao_dispara_para_guarda_de_nome_nao_medido(self) -> None:
        saida = _avaliar(
            "def f(a, flag):\n    if flag is None:\n        flag = a - 1\n    return flag\n"
        )
        assert saida["achados"] == []


class TestErroDeSintaxeEConteudoAusente:
    def test_erro_de_sintaxe_retorna_vazio(self) -> None:
        saida = _avaliar("def (:\n")
        assert saida["achados"] == []

    def test_conteudo_none_retorna_vazio(self) -> None:
        saida = _avaliar(None)
        assert saida["achados"] == []


class TestEntradaInvalida:
    def test_levanta_excecao_sem_campo_caminho(self) -> None:
        with pytest.raises(EntradaInvalida):
            avaliar_ora006({"conteudo": "x"}, _contexto())


class TestCertificacao:
    def test_implementacao_real_passa_na_certificacao(self) -> None:
        impl = construir_implementacao()
        contexto = _contexto()
        entrada_idempotencia = {
            "caminho": "src/x.py",
            "conteudo": (
                "def f(a, b):\n"
                "    x = medir(a)\n"
                "    if x is None:\n"
                "        x = a - b\n"
                "    return x\n"
            ),
            "regra": {},
        }
        definicao_certificada = certificar(
            impl,
            entrada_para_teste_idempotencia=entrada_idempotencia,
            contexto_para_teste_idempotencia=contexto,
        )
        assert definicao_certificada.status == StatusCapability.ACTIVE
