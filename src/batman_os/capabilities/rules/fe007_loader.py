"""Loader do spec bespoke FE-007 (`specs/fe007/*.json`) — mesmo padrão de
`a11y003_loader.py`: só 1 código, não generalizado em Skill."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from batman_os.capabilities.rules.fe007_nav_lock import RegraFe007Spec
from batman_os.capabilities.rules.lote_01 import SpecInvalido

_DIR_SPECS = Path(__file__).parent / "specs" / "fe007"


class SpecFe007(TypedDict):
    regra: RegraFe007Spec
    descoberta: dict[str, Any]


def _carregar_arquivo(caminho: Path) -> SpecFe007:
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    if "regra" not in bruto or "descoberta" not in bruto:
        raise SpecInvalido(f"{caminho.name}: esperava as chaves 'regra' e 'descoberta'")
    return SpecFe007(
        regra=RegraFe007Spec.model_validate(bruto["regra"]), descoberta=bruto["descoberta"]
    )


def carregar_especificacoes_fe007() -> list[SpecFe007]:
    return [_carregar_arquivo(caminho) for caminho in sorted(_DIR_SPECS.glob("*.json"))]
