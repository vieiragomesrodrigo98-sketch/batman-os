"""Loader dos specs da Skill "parsing TOML real de pyproject.toml"
(`specs/toml_dependencias/*.json`) — Milestone 3, Skill 5.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from batman_os.capabilities.rules.lote_01 import SpecInvalido
from batman_os.capabilities.rules.toml_dependencias import RegraDependenciasSpec

_DIR_SPECS = Path(__file__).parent / "specs" / "toml_dependencias"


class SpecDeRegraDependencias(TypedDict):
    regra: RegraDependenciasSpec
    descoberta: dict[str, Any]


def _carregar_arquivo(caminho: Path) -> SpecDeRegraDependencias:
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    if "regra" not in bruto or "descoberta" not in bruto:
        raise SpecInvalido(f"{caminho.name}: esperava as chaves 'regra' e 'descoberta'")
    return SpecDeRegraDependencias(
        regra=RegraDependenciasSpec.model_validate(bruto["regra"]),
        descoberta=bruto["descoberta"],
    )


def carregar_especificacoes_dependencias() -> list[SpecDeRegraDependencias]:
    return [_carregar_arquivo(caminho) for caminho in sorted(_DIR_SPECS.glob("*.json"))]
