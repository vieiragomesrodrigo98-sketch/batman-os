"""Testes da Capability bespoke COMP-008 (Vol.IV Cap.17)."""

from __future__ import annotations

import pytest

from batman_os.capabilities.capability_contract import certificar
from batman_os.capabilities.operator import ExecutionContext
from batman_os.capabilities.rules.comp008_relatorio_impacto_sem_disclaimer import (
    EntradaInvalida,
    avaliar_comp008,
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
    def test_dispara_por_nome_de_arquivo_sem_disclaimer(self) -> None:
        entrada = {
            "caminho": "frontend/src/pages/RelatorioImpacto.tsx",
            "conteudo": "<p>Resumo do mes</p>\n",
            "regra": {},
        }
        saida = avaliar_comp008(entrada, _contexto())
        assert len(saida["achados"]) == 1
        assert saida["achados"][0]["chave"] == ""

    def test_dispara_por_duas_metricas_em_arquivo_de_nome_neutro(self) -> None:
        entrada = {
            "caminho": "frontend/src/pages/Resumo.tsx",
            "conteudo": "<p>Sinais recebidos: 12</p>\n<p>Horas economizadas: 3</p>\n",
            "regra": {},
        }
        saida = avaliar_comp008(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_dispara_para_gerador_python_em_api_services(self) -> None:
        entrada = {
            "caminho": "api/services/relatorio_valor.py",
            "conteudo": "def gerar():\n    return {}\n",
            "regra": {},
        }
        saida = avaliar_comp008(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_com_uma_metrica_so(self) -> None:
        entrada = {
            "caminho": "frontend/src/pages/Resumo.tsx",
            "conteudo": "<p>Sinais recebidos: 12</p>\n",
            "regra": {},
        }
        saida = avaliar_comp008(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_quando_ha_disclaimer_cvm(self) -> None:
        entrada = {
            "caminho": "frontend/src/pages/RelatorioImpacto.tsx",
            "conteudo": "<p>Sinais recebidos</p>\n<p>Disclaimer CVM aqui</p>\n",
            "regra": {},
        }
        saida = avaliar_comp008(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_quando_ha_disclaimer_nao_constitui_promessa(self) -> None:
        entrada = {
            "caminho": "frontend/src/pages/RelatorioImpacto.tsx",
            "conteudo": (
                "<p>Sinais recebidos: 12</p>\n<p>Horas economizadas: 3</p>\n"
                "<p>Este histórico não constitui promessa de rentabilidade.</p>\n"
            ),
            "regra": {},
        }
        saida = avaliar_comp008(entrada, _contexto())
        assert saida["achados"] == []

    def test_conteudo_none_retorna_vazio(self) -> None:
        entrada: dict[str, object] = {
            "caminho": "frontend/src/pages/RelatorioImpacto.tsx",
            "conteudo": None,
            "regra": {},
        }
        saida = avaliar_comp008(entrada, _contexto())
        assert saida["achados"] == []


class TestEntradaInvalida:
    def test_levanta_excecao_sem_campo_caminho(self) -> None:
        with pytest.raises(EntradaInvalida):
            avaliar_comp008({"conteudo": "x"}, _contexto())


class TestCertificacao:
    def test_implementacao_real_passa_na_certificacao(self) -> None:
        impl = construir_implementacao()
        contexto = _contexto()
        entrada_idempotencia = {
            "caminho": "frontend/src/pages/RelatorioImpacto.tsx",
            "conteudo": "<p>Sinais recebidos</p>\n",
            "regra": {},
        }
        definicao_certificada = certificar(
            impl,
            entrada_para_teste_idempotencia=entrada_idempotencia,
            contexto_para_teste_idempotencia=contexto,
        )
        assert definicao_certificada.status == StatusCapability.ACTIVE
