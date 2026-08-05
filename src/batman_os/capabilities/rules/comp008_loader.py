"""Loader do spec bespoke COMP-008 (`specs/comp008/*.json`) — mesmo padrão
de `ora005_loader.py`: só 1 código, mas 2 entradas (frontend .ts/.tsx +
`api/services` .py — mesma convenção de múltiplas entradas por código do
lote_03, ex. A11Y-007/MOB-002, replicando os 2 alvos do legado)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from batman_os.capabilities.rules.comp008_relatorio_impacto_sem_disclaimer import (
    RegraComp008Spec,
)
from batman_os.capabilities.rules.lote_01 import SpecInvalido

_DIR_SPECS = Path(__file__).parent / "specs" / "comp008"


class SpecComp008(TypedDict):
    regra: RegraComp008Spec
    descoberta: dict[str, Any]


def _carregar_arquivo(caminho: Path) -> SpecComp008:
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    if "regra" not in bruto or "descoberta" not in bruto:
        raise SpecInvalido(f"{caminho.name}: esperava as chaves 'regra' e 'descoberta'")
    return SpecComp008(
        regra=RegraComp008Spec.model_validate(bruto["regra"]), descoberta=bruto["descoberta"]
    )


def carregar_especificacoes_comp008() -> list[SpecComp008]:
    return [_carregar_arquivo(caminho) for caminho in sorted(_DIR_SPECS.glob("*.json"))]
