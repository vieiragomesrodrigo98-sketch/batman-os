"""Loader do spec bespoke QAVIS-001 (`specs/qavis001/*.json`) — mesmo
padrão de `sweep001_loader.py`: só 1 código, não generalizado em Skill."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from batman_os.capabilities.rules.lote_01 import SpecInvalido
from batman_os.capabilities.rules.qavis001_playwright_falhou import RegraQaVis001Spec

_DIR_SPECS = Path(__file__).parent / "specs" / "qavis001"


class SpecQaVis001(TypedDict):
    regra: RegraQaVis001Spec
    descoberta: dict[str, Any]


def _carregar_arquivo(caminho: Path) -> SpecQaVis001:
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    if "regra" not in bruto or "descoberta" not in bruto:
        raise SpecInvalido(f"{caminho.name}: esperava as chaves 'regra' e 'descoberta'")
    return SpecQaVis001(
        regra=RegraQaVis001Spec.model_validate(bruto["regra"]), descoberta=bruto["descoberta"]
    )


def carregar_especificacoes_qavis001() -> list[SpecQaVis001]:
    return [_carregar_arquivo(caminho) for caminho in sorted(_DIR_SPECS.glob("*.json"))]
