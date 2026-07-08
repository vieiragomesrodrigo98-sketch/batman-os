"""Loader do spec bespoke SWEEP-001 (`specs/sweep001/*.json`) — mesmo
padrão de `a11y003_loader.py`: só 1 código, não generalizado em Skill."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from batman_os.capabilities.rules.lote_01 import SpecInvalido
from batman_os.capabilities.rules.sweep001_cadencia_quebrada import RegraSweep001Spec

_DIR_SPECS = Path(__file__).parent / "specs" / "sweep001"


class SpecSweep001(TypedDict):
    regra: RegraSweep001Spec
    descoberta: dict[str, Any]


def _carregar_arquivo(caminho: Path) -> SpecSweep001:
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    if "regra" not in bruto or "descoberta" not in bruto:
        raise SpecInvalido(f"{caminho.name}: esperava as chaves 'regra' e 'descoberta'")
    return SpecSweep001(
        regra=RegraSweep001Spec.model_validate(bruto["regra"]), descoberta=bruto["descoberta"]
    )


def carregar_especificacoes_sweep001() -> list[SpecSweep001]:
    return [_carregar_arquivo(caminho) for caminho in sorted(_DIR_SPECS.glob("*.json"))]
