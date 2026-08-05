"""Testes da Capability bespoke FIN-006 (Vol.IV Cap.17)."""

from __future__ import annotations

import pytest

from batman_os.capabilities.capability_contract import certificar
from batman_os.capabilities.operator import ExecutionContext
from batman_os.capabilities.rules.fin006_significancia_sem_cluster import (
    EntradaInvalida,
    avaliar_fin006,
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
    def test_dispara_para_t_do_ic_com_retorno_sem_cluster(self) -> None:
        entrada = {
            "caminho": "scripts/backtest_ic.py",
            "conteudo": "t = ic * sqrt(len(retornos) - 3)\n",
        }
        saida = avaliar_fin006(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_dispara_para_ttest_1samp_em_serie_de_retornos(self) -> None:
        entrada = {
            "caminho": "src/radar/validation/sig.py",
            "conteudo": "res = stats.ttest_1samp(returns, 0)\n",
        }
        saida = avaliar_fin006(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_dispara_para_forma_potencia_meio(self) -> None:
        entrada = {
            "caminho": "scripts/backtest_ic.py",
            "conteudo": "retorno = serie.mean()\nt = ic * (n - 3) ** 0.5\n",
        }
        saida = avaliar_fin006(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_descricao_reporta_linhas_do_t_ingenuo(self) -> None:
        entrada = {
            "caminho": "scripts/backtest_ic.py",
            "conteudo": "retorno = 1\nt = ic * sqrt(len(xs) - 3)\n",
        }
        saida = avaliar_fin006(entrada, _contexto())
        assert "(linhas 2)" in saida["achados"][0]["descricao"]
        assert "t inflado por ~raiz(N/dias)" in saida["achados"][0]["descricao"]

    def test_nao_dispara_sem_vocabulario_de_retorno(self) -> None:
        # t-teste em latência de endpoint não sofre cluster por pregão —
        # fora do escopo da regra (mesma nota do legado).
        entrada = {
            "caminho": "scripts/perf.py",
            "conteudo": "t = x * sqrt(len(amostras) - 3)\nlatencia_ms = medir()\n",
        }
        saida = avaliar_fin006(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_com_groupby_por_data(self) -> None:
        entrada = {
            "caminho": "scripts/backtest_ic.py",
            "conteudo": (
                "medias = df.groupby('data')['retorno'].mean()\nt = ic * sqrt(len(medias) - 3)\n"
            ),
        }
        saida = avaliar_fin006(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_com_dt_date(self) -> None:
        entrada = {
            "caminho": "scripts/backtest_ic.py",
            "conteudo": "dias = df['ts'].dt.date\nt = ic * sqrt(len(retornos) - 3)\n",
        }
        saida = avaliar_fin006(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_sem_t_ingenuo(self) -> None:
        entrada = {
            "caminho": "scripts/backtest_ic.py",
            "conteudo": "retorno = serie.mean()\n",
        }
        saida = avaliar_fin006(entrada, _contexto())
        assert saida["achados"] == []

    def test_conteudo_none_retorna_vazio(self) -> None:
        entrada: dict[str, object] = {"caminho": "scripts/x.py", "conteudo": None}
        saida = avaliar_fin006(entrada, _contexto())
        assert saida["achados"] == []


class TestEntradaInvalida:
    def test_levanta_excecao_sem_campo_caminho(self) -> None:
        with pytest.raises(EntradaInvalida):
            avaliar_fin006({"conteudo": "x"}, _contexto())


class TestCertificacao:
    def test_implementacao_real_passa_na_certificacao(self) -> None:
        impl = construir_implementacao()
        contexto = _contexto()
        entrada_idempotencia = {
            "caminho": "scripts/backtest_ic.py",
            "conteudo": "t = ic * sqrt(len(retornos) - 3)\n",
        }
        definicao_certificada = certificar(
            impl,
            entrada_para_teste_idempotencia=entrada_idempotencia,
            contexto_para_teste_idempotencia=contexto,
        )
        assert definicao_certificada.status == StatusCapability.ACTIVE
