"""Testes do loader do spec bespoke COMP-008 (`comp008_loader.py`)."""

from __future__ import annotations

from batman_os.capabilities.rules.comp008_loader import carregar_especificacoes_comp008
from batman_os.capabilities.rules.comp008_relatorio_impacto_sem_disclaimer import (
    RegraComp008Spec,
)


class TestCarregarEspecificacoesComp008:
    def test_carrega_o_codigo_comp008_em_duas_entradas(self) -> None:
        specs = carregar_especificacoes_comp008()

        codigos = {item["regra"].codigo for item in specs}
        assert codigos == {"COMP-008"}
        # 2 entradas para o mesmo código (frontend .ts/.tsx + api/services
        # .py), replicando os 2 alvos do legado — mesma convenção de
        # múltiplas entradas do lote_03 (A11Y-007/MOB-002).
        assert len(specs) == 2

    def test_toda_regra_e_uma_regracomp008spec_valida(self) -> None:
        specs = carregar_especificacoes_comp008()

        for item in specs:
            assert isinstance(item["regra"], RegraComp008Spec)

    def test_descobertas_cobrem_frontend_e_api_services(self) -> None:
        specs = carregar_especificacoes_comp008()

        escopos = {tuple(item["descoberta"]["scope_dirs"]) for item in specs}
        assert escopos == {("frontend/src",), ("api/services",)}
        for item in specs:
            assert item["descoberta"]["tipo"] == "arvore"

    def test_toda_descoberta_exclui_admin_e_testes(self) -> None:
        # replica o `_ALLOWED_RE` do legado, aplicado aos DOIS alvos.
        specs = carregar_especificacoes_comp008()

        for item in specs:
            assert item["descoberta"]["excluir_caminho_contem_lower"] == [
                "pages/admin/",
                "components/admin/",
                ".test.",
                "__tests__",
            ]
