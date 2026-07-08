"""Testes do loader dos specs da Skill "regex agregado sobre múltiplos
arquivos" (`regex_agregado_multi_arquivo_loader.py` — continuação da
migração)."""

from __future__ import annotations

from batman_os.capabilities.rules.regex_agregado_multi_arquivo import RegraAgregadaSpec
from batman_os.capabilities.rules.regex_agregado_multi_arquivo_loader import (
    carregar_especificacoes_agregadas,
)

_TIPOS_DESCOBERTA_VALIDOS = {"regex_agregado"}


class TestCarregarEspecificacoesAgregadas:
    def test_carrega_pelo_menos_8_codigos_distintos(self) -> None:
        specs = carregar_especificacoes_agregadas()

        codigos = {item["regra"].codigo for item in specs}
        assert len(codigos) >= 8

    def test_toda_regra_e_uma_regraagregadaspec_valida(self) -> None:
        specs = carregar_especificacoes_agregadas()

        for item in specs:
            assert isinstance(item["regra"], RegraAgregadaSpec)
            assert item["regra"].modo in ("presenca", "ausencia")

    def test_toda_descoberta_tem_tipo_reconhecido(self) -> None:
        specs = carregar_especificacoes_agregadas()

        for item in specs:
            assert item["descoberta"]["tipo"] in _TIPOS_DESCOBERTA_VALIDOS

    def test_sem_codigos_duplicados(self) -> None:
        specs = carregar_especificacoes_agregadas()

        codigos = [item["regra"].codigo for item in specs]
        assert len(codigos) == len(set(codigos))
