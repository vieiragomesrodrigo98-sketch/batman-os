"""Testes do loader do spec bespoke ORA-006 (`ora006_loader.py`)."""

from __future__ import annotations

from batman_os.capabilities.rules.ora005_loader import carregar_especificacoes_ora005
from batman_os.capabilities.rules.ora006_loader import carregar_especificacoes_ora006
from batman_os.capabilities.rules.ora006_proxy_medicao_silenciosa import RegraOra006Spec


class TestCarregarEspecificacoesOra006:
    def test_carrega_o_codigo_confirmado(self) -> None:
        specs = carregar_especificacoes_ora006()

        codigos = {item["regra"].codigo for item in specs}
        assert codigos == {"ORA-006"}

    def test_toda_regra_e_uma_regraora006spec_valida(self) -> None:
        specs = carregar_especificacoes_ora006()

        for item in specs:
            assert isinstance(item["regra"], RegraOra006Spec)

    def test_descoberta_espelha_a_da_ora005(self) -> None:
        # mesmo `_FALLBACK_DIRS = ("src", "api")` + exclusão de testes do
        # legado — ORA-005 e ORA-006 compartilham o escopo em oracle.py.
        [spec_ora006] = carregar_especificacoes_ora006()
        [spec_ora005] = carregar_especificacoes_ora005()

        assert spec_ora006["descoberta"] == spec_ora005["descoberta"]
