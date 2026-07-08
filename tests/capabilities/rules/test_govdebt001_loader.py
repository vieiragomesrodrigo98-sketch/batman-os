"""Testes do loader do spec bespoke GOVDEBT-001 (`govdebt001_loader.py`)."""

from __future__ import annotations

from batman_os.capabilities.rules.govdebt001_finding_sem_decisao import RegraGovdebt001Spec
from batman_os.capabilities.rules.govdebt001_loader import carregar_especificacoes_govdebt001


class TestCarregarEspecificacoesGovdebt001:
    def test_carrega_o_codigo_govdebt001(self) -> None:
        specs = carregar_especificacoes_govdebt001()

        codigos = {item["regra"].codigo for item in specs}
        assert codigos == {"GOVDEBT-001"}

    def test_toda_regra_e_uma_regragovdebt001spec_valida(self) -> None:
        specs = carregar_especificacoes_govdebt001()

        for item in specs:
            assert isinstance(item["regra"], RegraGovdebt001Spec)

    def test_descoberta_e_do_tipo_govdebt001(self) -> None:
        specs = carregar_especificacoes_govdebt001()

        for item in specs:
            assert item["descoberta"]["tipo"] == "govdebt001"
