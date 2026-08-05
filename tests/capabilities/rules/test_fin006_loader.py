"""Testes do loader do spec bespoke FIN-006 (`fin006_loader.py`)."""

from __future__ import annotations

from batman_os.capabilities.rules.fin006_loader import carregar_especificacoes_fin006
from batman_os.capabilities.rules.fin006_significancia_sem_cluster import RegraFin006Spec


class TestCarregarEspecificacoesFin006:
    def test_carrega_o_codigo_fin006(self) -> None:
        specs = carregar_especificacoes_fin006()

        codigos = {item["regra"].codigo for item in specs}
        assert codigos == {"FIN-006"}

    def test_toda_regra_e_uma_regrafin006spec_valida(self) -> None:
        specs = carregar_especificacoes_fin006()

        for item in specs:
            assert isinstance(item["regra"], RegraFin006Spec)

    def test_descoberta_inclui_scripts_alem_de_src_dirs(self) -> None:
        # A estatística do projeto motivador mora em `scripts/`, que NÃO
        # está em src_dirs — legado: `for d in (*ctx.src_dirs, "scripts")`.
        specs = carregar_especificacoes_fin006()

        for item in specs:
            assert item["descoberta"]["tipo"] == "arvore"
            assert item["descoberta"]["scope_dirs"] == [
                "api",
                "src",
                "dashboard",
                "pages",
                "scripts",
            ]
