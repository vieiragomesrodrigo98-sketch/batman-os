"""Testes do loader dos specs da Skill "métrica com limiar"
(`metrica_com_limiar_loader.py` — continuação da migração)."""

from __future__ import annotations

from batman_os.capabilities.rules.metrica_com_limiar import MetricaTipo, RegraMetricaSpec
from batman_os.capabilities.rules.metrica_com_limiar_loader import (
    carregar_especificacoes_metrica,
)

_TIPOS_DESCOBERTA_VALIDOS = {"arquivo_fixo", "arvore", "glob"}


class TestCarregarEspecificacoesMetrica:
    def test_carrega_pelo_menos_7_codigos_distintos(self) -> None:
        specs = carregar_especificacoes_metrica()

        codigos = {item["regra"].codigo for item in specs}
        assert len(codigos) >= 7

    def test_toda_regra_e_uma_regrametricaspec_valida(self) -> None:
        specs = carregar_especificacoes_metrica()

        for item in specs:
            assert isinstance(item["regra"], RegraMetricaSpec)
            assert item["regra"].metrica in MetricaTipo
            assert item["regra"].operador in (">", ">=")

    def test_toda_descoberta_tem_tipo_reconhecido(self) -> None:
        specs = carregar_especificacoes_metrica()

        for item in specs:
            assert item["descoberta"]["tipo"] in _TIPOS_DESCOBERTA_VALIDOS

    def test_sem_codigos_duplicados(self) -> None:
        specs = carregar_especificacoes_metrica()

        codigos = [item["regra"].codigo for item in specs]
        assert len(codigos) == len(set(codigos))
