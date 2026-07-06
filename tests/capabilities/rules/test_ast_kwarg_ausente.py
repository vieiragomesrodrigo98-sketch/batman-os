"""Testes da Skill AST "Call com kwarg obrigatório ausente" (Vol.IV Cap.17)."""

from __future__ import annotations

import pytest

from batman_os.capabilities.capability_contract import certificar
from batman_os.capabilities.operator import ExecutionContext
from batman_os.capabilities.rules.ast_kwarg_ausente import (
    EntradaInvalida,
    avaliar_regra_kwarg_ausente,
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


def _regra(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "codigo": "TEST-001",
        "agente": "teste",
        "severidade": "high",
        "categoria": "cat",
        "titulo": "titulo",
        "causa": "causa",
        "remediacao": "remediacao",
        "metodos_call": ["get", "post"],
        "kwarg_obrigatorio": "timeout",
        "objeto_attr_permitido": [],
        "objeto_name_permitido": [],
    }
    base.update(overrides)
    return base


class TestDisparo:
    def test_dispara_quando_kwarg_ausente(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": "requests.get('http://x')\n",
            "regra": _regra(objeto_name_permitido=["requests"]),
        }
        saida = avaliar_regra_kwarg_ausente(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_quando_kwarg_presente(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": "requests.get('http://x', timeout=10)\n",
            "regra": _regra(objeto_name_permitido=["requests"]),
        }
        saida = avaliar_regra_kwarg_ausente(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_quando_metodo_nao_esta_na_lista(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": "requests.delete('http://x')\n",
            "regra": _regra(objeto_name_permitido=["requests"]),
        }
        saida = avaliar_regra_kwarg_ausente(entrada, _contexto())
        assert saida["achados"] == []


class TestFiltroObjeto:
    def test_nao_dispara_quando_objeto_name_nao_bate(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": "outra_lib.get('http://x')\n",
            "regra": _regra(objeto_name_permitido=["requests", "httpx"]),
        }
        saida = avaliar_regra_kwarg_ausente(entrada, _contexto())
        assert saida["achados"] == []

    def test_dispara_para_objeto_attr_permitido(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": "self.client.get('http://x')\n",
            "regra": _regra(objeto_attr_permitido=["client", "session"]),
        }
        saida = avaliar_regra_kwarg_ausente(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_sem_filtro_de_objeto_aceita_qualquer_base(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": "qualquer_coisa.get('http://x')\n",
            "regra": _regra(),
        }
        saida = avaliar_regra_kwarg_ausente(entrada, _contexto())
        assert len(saida["achados"]) == 1


class TestErroDeSintaxeEConteudoAusente:
    def test_conteudo_com_erro_de_sintaxe_retorna_vazio(self) -> None:
        entrada = {"caminho": "a.py", "conteudo": "def (:\n", "regra": _regra()}
        saida = avaliar_regra_kwarg_ausente(entrada, _contexto())
        assert saida["achados"] == []

    def test_conteudo_none_retorna_vazio(self) -> None:
        entrada = {"caminho": "a.py", "conteudo": None, "regra": _regra()}
        saida = avaliar_regra_kwarg_ausente(entrada, _contexto())
        assert saida["achados"] == []


class TestEntradaInvalida:
    def test_levanta_excecao_sem_campo_regra(self) -> None:
        with pytest.raises(EntradaInvalida):
            avaliar_regra_kwarg_ausente({"caminho": "a.py"}, _contexto())


class TestCertificacao:
    def test_implementacao_real_passa_na_certificacao(self) -> None:
        impl = construir_implementacao()
        contexto = _contexto()
        entrada_idempotencia = {
            "caminho": "a.py",
            "conteudo": "requests.get('http://x')\n",
            "regra": _regra(objeto_name_permitido=["requests"]),
        }
        definicao_certificada = certificar(
            impl,
            entrada_para_teste_idempotencia=entrada_idempotencia,
            contexto_para_teste_idempotencia=contexto,
        )
        assert definicao_certificada.status == StatusCapability.ACTIVE
