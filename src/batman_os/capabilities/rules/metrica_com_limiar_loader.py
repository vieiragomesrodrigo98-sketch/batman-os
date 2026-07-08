"""Loader dos specs da Skill "métrica com limiar"
(`specs/metrica_com_limiar/*.json` — continuação da migração). Mesmo
padrão de `lote_01.py`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from batman_os.capabilities.rules.lote_01 import SpecInvalido
from batman_os.capabilities.rules.metrica_com_limiar import RegraMetricaSpec

_DIR_SPECS = Path(__file__).parent / "specs" / "metrica_com_limiar"


class SpecDeRegraMetrica(TypedDict):
    regra: RegraMetricaSpec
    descoberta: dict[str, Any]


def _carregar_arquivo(caminho: Path) -> SpecDeRegraMetrica:
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    if "regra" not in bruto or "descoberta" not in bruto:
        raise SpecInvalido(f"{caminho.name}: esperava as chaves 'regra' e 'descoberta'")
    return SpecDeRegraMetrica(
        regra=RegraMetricaSpec.model_validate(bruto["regra"]), descoberta=bruto["descoberta"]
    )


def carregar_especificacoes_metrica() -> list[SpecDeRegraMetrica]:
    return [_carregar_arquivo(caminho) for caminho in sorted(_DIR_SPECS.glob("*.json"))]
