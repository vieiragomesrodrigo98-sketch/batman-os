"""Testes do loader do spec bespoke FE-API (`feapi_loader.py`)."""

from __future__ import annotations

from batman_os.capabilities.rules.feapi_loader import carregar_especificacoes_feapi
from batman_os.capabilities.rules.feapi_rota_sem_frontend import RegraFeApiSpec


class TestCarregarEspecificacoesFeApi:
    def test_carrega_o_codigo_feapi(self) -> None:
        specs = carregar_especificacoes_feapi()

        codigos = {item["regra"].codigo for item in specs}
        assert codigos == {"FE-API"}

    def test_toda_regra_e_uma_regrafeapispec_valida(self) -> None:
        specs = carregar_especificacoes_feapi()

        for item in specs:
            assert isinstance(item["regra"], RegraFeApiSpec)

    def test_descoberta_e_do_tipo_feapi(self) -> None:
        specs = carregar_especificacoes_feapi()

        for item in specs:
            assert item["descoberta"]["tipo"] == "feapi"
