"""Testes de `capabilities/isencoes.py` — isenções pré-registradas
(allowlist com motivo+validade) da Onda 1 do Plano Cobertura Total
(recalibração de regras, S162)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from batman_os.capabilities.isencoes import (
    IsencaoPreRegistrada,
    carregar_isencoes,
    esta_isento,
    filtrar_achados_isentos,
)


@dataclass
class _AchadoFake:
    codigo: str
    arquivo: str


def _isencao(**overrides: object) -> IsencaoPreRegistrada:
    base: dict[str, object] = {
        "codigo": "RISK-005",
        "caminho": "src/radar/lab/momentum_backtest.py",
        "motivo": "modulo de pesquisa pura pre-registrado",
        "validade": "2027-01-31",
    }
    base.update(overrides)
    return IsencaoPreRegistrada.model_validate(base)


class TestEstaIsento:
    def test_codigo_e_caminho_batem_e_validade_no_futuro(self) -> None:
        isencoes = [_isencao()]
        assert esta_isento(
            "RISK-005",
            "src/radar/lab/momentum_backtest.py",
            isencoes,
            hoje=date(2026, 8, 1),
        )

    def test_codigo_diferente_nao_isenta(self) -> None:
        isencoes = [_isencao()]
        assert not esta_isento(
            "FIN-005", "src/radar/lab/momentum_backtest.py", isencoes, hoje=date(2026, 8, 1)
        )

    def test_caminho_diferente_nao_isenta(self) -> None:
        isencoes = [_isencao()]
        assert not esta_isento("RISK-005", "src/radar/outro.py", isencoes, hoje=date(2026, 8, 1))

    def test_isencao_expirada_deixa_de_suprimir(self) -> None:
        isencoes = [_isencao(validade="2026-01-01")]
        assert not esta_isento(
            "RISK-005",
            "src/radar/lab/momentum_backtest.py",
            isencoes,
            hoje=date(2026, 8, 1),
        )

    def test_normaliza_separador_de_caminho_windows(self) -> None:
        isencoes = [_isencao(caminho="src/radar/lab/momentum_backtest.py")]
        assert esta_isento(
            "RISK-005",
            "src\\radar\\lab\\momentum_backtest.py",
            isencoes,
            hoje=date(2026, 8, 1),
        )


class TestFiltrarAchadosIsentos:
    def test_remove_so_o_achado_isento(self) -> None:
        achados = [
            _AchadoFake("RISK-005", "src/radar/lab/momentum_backtest.py"),
            _AchadoFake("RISK-005", "src/radar/outro_arquivo.py"),
        ]
        restantes = filtrar_achados_isentos(achados, [_isencao()], hoje=date(2026, 8, 1))
        assert [a.arquivo for a in restantes] == ["src/radar/outro_arquivo.py"]

    def test_lista_vazia_de_isencoes_nao_filtra_nada(self) -> None:
        achados = [_AchadoFake("RISK-005", "src/radar/lab/momentum_backtest.py")]
        assert filtrar_achados_isentos(achados, []) == achados


class TestCarregarIsencoes:
    def test_arquivo_ausente_retorna_lista_vazia(self, tmp_path: Path) -> None:
        assert carregar_isencoes(tmp_path / "nao-existe.json") == []

    def test_carrega_entradas_do_arquivo(self, tmp_path: Path) -> None:
        arq = tmp_path / "isencoes.json"
        arq.write_text(
            json.dumps(
                {
                    "isencoes": [
                        {
                            "codigo": "RISK-005",
                            "caminho": "a.py",
                            "motivo": "m",
                            "validade": "2027-01-01",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        isencoes = carregar_isencoes(arq)
        assert len(isencoes) == 1
        assert isencoes[0].codigo == "RISK-005"

    def test_default_carrega_o_arquivo_real_do_pacote(self) -> None:
        """O arquivo `isencoes_pre_registradas.json` real (commitado) tem
        as 2 isenções do momentum_backtest.py (RISK-005/FIN-005, S162)."""
        isencoes = carregar_isencoes()
        pares = {(i.codigo, i.caminho) for i in isencoes}
        assert ("RISK-005", "src/radar/lab/momentum_backtest.py") in pares
        assert ("FIN-005", "src/radar/lab/momentum_backtest.py") in pares
