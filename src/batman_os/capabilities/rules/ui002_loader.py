"""Loader do spec bespoke UI-002 (`specs/ui002/*.json`) — mesmo padrão de
`a11y003_loader.py`: só 1 código, não generalizado em Skill."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from batman_os.capabilities.rules.lote_01 import SpecInvalido
from batman_os.capabilities.rules.ui002_inline_style_estatico import RegraUi002Spec

_DIR_SPECS = Path(__file__).parent / "specs" / "ui002"


class SpecUi002(TypedDict):
    regra: RegraUi002Spec
    descoberta: dict[str, Any]


def _carregar_arquivo(caminho: Path) -> SpecUi002:
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    if "regra" not in bruto or "descoberta" not in bruto:
        raise SpecInvalido(f"{caminho.name}: esperava as chaves 'regra' e 'descoberta'")
    return SpecUi002(
        regra=RegraUi002Spec.model_validate(bruto["regra"]), descoberta=bruto["descoberta"]
    )


def carregar_especificacoes_ui002() -> list[SpecUi002]:
    return [_carregar_arquivo(caminho) for caminho in sorted(_DIR_SPECS.glob("*.json"))]
