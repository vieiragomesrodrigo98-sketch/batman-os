"""Loader dos specs da Skill "regex agregado sobre múltiplos arquivos"
(`specs/regex_agregado_multi_arquivo/*.json` — continuação da migração).
Mesmo padrão de `lote_01.py`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from batman_os.capabilities.rules.lote_01 import SpecInvalido
from batman_os.capabilities.rules.regex_agregado_multi_arquivo import RegraAgregadaSpec

_DIR_SPECS = Path(__file__).parent / "specs" / "regex_agregado_multi_arquivo"


class SpecDeRegraAgregada(TypedDict):
    regra: RegraAgregadaSpec
    descoberta: dict[str, Any]


def _carregar_arquivo(caminho: Path) -> SpecDeRegraAgregada:
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    if "regra" not in bruto or "descoberta" not in bruto:
        raise SpecInvalido(f"{caminho.name}: esperava as chaves 'regra' e 'descoberta'")
    return SpecDeRegraAgregada(
        regra=RegraAgregadaSpec.model_validate(bruto["regra"]), descoberta=bruto["descoberta"]
    )


def carregar_especificacoes_agregadas() -> list[SpecDeRegraAgregada]:
    return [_carregar_arquivo(caminho) for caminho in sorted(_DIR_SPECS.glob("*.json"))]
