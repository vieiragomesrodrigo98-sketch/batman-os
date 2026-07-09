"""Testes do loader do spec bespoke FE-002 (`fe002_loader.py`)."""

from __future__ import annotations

from batman_os.capabilities.rules.fe002_loader import carregar_especificacoes_fe002
from batman_os.capabilities.rules.fe002_tofixed_sem_null_safety import RegraFe002Spec


class TestCarregarEspecificacoesFe002:
    def test_carrega_o_codigo_fe002(self) -> None:
        specs = carregar_especificacoes_fe002()

        codigos = {item["regra"].codigo for item in specs}
        assert codigos == {"FE-002"}

    def test_toda_regra_e_uma_regrafe002spec_valida(self) -> None:
        specs = carregar_especificacoes_fe002()

        for item in specs:
            assert isinstance(item["regra"], RegraFe002Spec)

    def test_descoberta_e_do_tipo_arvore(self) -> None:
        specs = carregar_especificacoes_fe002()

        for item in specs:
            assert item["descoberta"]["tipo"] == "arvore"
