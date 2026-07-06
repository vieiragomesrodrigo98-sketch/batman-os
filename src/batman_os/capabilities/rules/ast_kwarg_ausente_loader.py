"""Loader dos specs da Skill AST "Call com kwarg obrigatório ausente"
(`specs/ast_kwarg_ausente/*.json`) — Milestone 3, Skill 2. Mesmo padrão de
`lote_01.py`/`ast_padrao_ausente_loader.py`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from batman_os.capabilities.rules.ast_kwarg_ausente import RegraKwargAusenteSpec
from batman_os.capabilities.rules.lote_01 import SpecInvalido

_DIR_SPECS = Path(__file__).parent / "specs" / "ast_kwarg_ausente"


class SpecDeRegraKwargAusente(TypedDict):
    regra: RegraKwargAusenteSpec
    descoberta: dict[str, Any]


def _carregar_arquivo(caminho: Path) -> SpecDeRegraKwargAusente:
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    if "regra" not in bruto or "descoberta" not in bruto:
        raise SpecInvalido(f"{caminho.name}: esperava as chaves 'regra' e 'descoberta'")
    return SpecDeRegraKwargAusente(
        regra=RegraKwargAusenteSpec.model_validate(bruto["regra"]), descoberta=bruto["descoberta"]
    )


def carregar_especificacoes_kwarg_ausente() -> list[SpecDeRegraKwargAusente]:
    return [_carregar_arquivo(caminho) for caminho in sorted(_DIR_SPECS.glob("*.json"))]
