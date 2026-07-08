"""Loader dos specs da Skill "janela de contexto por ocorrência"
(`specs/janela_contexto_regex/*.json` — continuação da migração). Mesmo
padrão de `lote_01.py`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from batman_os.capabilities.rules.janela_contexto_regex import RegraJanelaSpec
from batman_os.capabilities.rules.lote_01 import SpecInvalido

_DIR_SPECS = Path(__file__).parent / "specs" / "janela_contexto_regex"


class SpecDeRegraJanela(TypedDict):
    regra: RegraJanelaSpec
    descoberta: dict[str, Any]


def _carregar_arquivo(caminho: Path) -> SpecDeRegraJanela:
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    if "regra" not in bruto or "descoberta" not in bruto:
        raise SpecInvalido(f"{caminho.name}: esperava as chaves 'regra' e 'descoberta'")
    return SpecDeRegraJanela(
        regra=RegraJanelaSpec.model_validate(bruto["regra"]), descoberta=bruto["descoberta"]
    )


def carregar_especificacoes_janela() -> list[SpecDeRegraJanela]:
    return [_carregar_arquivo(caminho) for caminho in sorted(_DIR_SPECS.glob("*.json"))]
