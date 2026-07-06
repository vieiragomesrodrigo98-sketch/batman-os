"""Testes da Capability bespoke ORA-005 (Vol.IV Cap.17)."""

from __future__ import annotations

import pytest

from batman_os.capabilities.capability_contract import certificar
from batman_os.capabilities.operator import ExecutionContext
from batman_os.capabilities.rules.ora005_fallback_silencioso import (
    EntradaInvalida,
    avaliar_ora005,
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


class TestDisparo:
    def test_dispara_para_except_amplo_com_return_sem_log(self) -> None:
        conteudo = (
            "def f():\n"
            "    try:\n"
            "        return calcular()\n"
            "    except Exception:\n"
            "        return _defaults\n"
        )
        entrada = {"caminho": "src/x.py", "conteudo": conteudo, "regra": {}}
        saida = avaliar_ora005(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_dispara_para_bare_except(self) -> None:
        conteudo = (
            "def f():\n    try:\n        return calcular()\n    except:\n        return _defaults\n"
        )
        entrada = {"caminho": "src/x.py", "conteudo": conteudo, "regra": {}}
        saida = avaliar_ora005(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_quando_loga(self) -> None:
        conteudo = (
            "def f():\n"
            "    try:\n"
            "        return calcular()\n"
            "    except Exception as e:\n"
            "        logger.warning(e)\n"
            "        return _defaults\n"
        )
        entrada = {"caminho": "src/x.py", "conteudo": conteudo, "regra": {}}
        saida = avaliar_ora005(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_quando_relevanta(self) -> None:
        conteudo = (
            "def f():\n    try:\n        return calcular()\n    except Exception:\n        raise\n"
        )
        entrada = {"caminho": "src/x.py", "conteudo": conteudo, "regra": {}}
        saida = avaliar_ora005(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_quando_excecao_especifica(self) -> None:
        conteudo = (
            "def f():\n"
            "    try:\n"
            "        return calcular()\n"
            "    except ValueError:\n"
            "        return _defaults\n"
        )
        entrada = {"caminho": "src/x.py", "conteudo": conteudo, "regra": {}}
        saida = avaliar_ora005(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_sem_return_no_handler(self) -> None:
        conteudo = "def f():\n    try:\n        x()\n    except Exception:\n        pass\n"
        entrada = {"caminho": "src/x.py", "conteudo": conteudo, "regra": {}}
        saida = avaliar_ora005(entrada, _contexto())
        assert saida["achados"] == []


class TestErroDeSintaxeEConteudoAusente:
    def test_erro_de_sintaxe_retorna_vazio(self) -> None:
        entrada = {"caminho": "src/x.py", "conteudo": "def (:\n", "regra": {}}
        saida = avaliar_ora005(entrada, _contexto())
        assert saida["achados"] == []

    def test_conteudo_none_retorna_vazio(self) -> None:
        entrada: dict[str, object] = {"caminho": "src/x.py", "conteudo": None, "regra": {}}
        saida = avaliar_ora005(entrada, _contexto())
        assert saida["achados"] == []


class TestEntradaInvalida:
    def test_levanta_excecao_sem_campo_caminho(self) -> None:
        with pytest.raises(EntradaInvalida):
            avaliar_ora005({"conteudo": "x"}, _contexto())


class TestCertificacao:
    def test_implementacao_real_passa_na_certificacao(self) -> None:
        impl = construir_implementacao()
        contexto = _contexto()
        entrada_idempotencia = {
            "caminho": "src/x.py",
            "conteudo": (
                "def f():\n    try:\n        x()\n    except Exception:\n        return d\n"
            ),
            "regra": {},
        }
        definicao_certificada = certificar(
            impl,
            entrada_para_teste_idempotencia=entrada_idempotencia,
            contexto_para_teste_idempotencia=contexto,
        )
        assert definicao_certificada.status == StatusCapability.ACTIVE
