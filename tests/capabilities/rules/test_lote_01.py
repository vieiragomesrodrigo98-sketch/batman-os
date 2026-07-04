"""Testes do loader do primeiro lote de migração (`capabilities/rules/lote_01.py`)."""

from __future__ import annotations

from batman_os.capabilities.rules.lote_01 import carregar_lote_01
from batman_os.capabilities.rules.regex_sobre_conteudo import ModoAvaliacao, RegraSpec

_CODIGOS_ESPERADOS = {
    "DEVOPS-003",
    "RED-005",
    "RED-007",
    "CLOUD-001",
    "NS-002",
    "SEC-014",
    "VPS-001",
    "VPS-002",
    "VPS-013",
    "CLOUD-007",
    "CLOUD-002",
    "DE-002",
    "FE-004",
    "AI-005",
}

_TIPOS_DESCOBERTA_VALIDOS = {"arquivo_fixo", "arvore", "glob"}


class TestCarregarLote01:
    def test_carrega_as_14_regras_esperadas(self) -> None:
        lote = carregar_lote_01()

        codigos = {item["regra"].codigo for item in lote}

        assert len(lote) == 14
        assert codigos == _CODIGOS_ESPERADOS

    def test_toda_regra_e_uma_regraspec_valida(self) -> None:
        lote = carregar_lote_01()

        for item in lote:
            assert isinstance(item["regra"], RegraSpec)
            assert item["regra"].modo in ModoAvaliacao

    def test_toda_descoberta_tem_tipo_reconhecido(self) -> None:
        lote = carregar_lote_01()

        for item in lote:
            assert item["descoberta"]["tipo"] in _TIPOS_DESCOBERTA_VALIDOS

    def test_regras_com_condicoes_adicionais_tem_a_chave_correta(self) -> None:
        lote = {item["regra"].codigo: item for item in carregar_lote_01()}

        assert len(lote["DEVOPS-003"]["descoberta"]["condicoes_adicionais"]) == 1
        assert len(lote["DE-002"]["descoberta"]["condicoes_adicionais"]) == 2
        assert len(lote["CLOUD-007"]["descoberta"]["condicoes_adicionais"]) == 1
