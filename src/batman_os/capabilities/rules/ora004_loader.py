"""Loader do spec bespoke ORA-004 (`specs/ora004/*.json`) — Milestone 3,
Skill 6. Mesmo padrão de `de003_loader.py`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from batman_os.capabilities.rules.lote_01 import SpecInvalido
from batman_os.capabilities.rules.ora004_status_typo import RegraOra004Spec

_DIR_SPECS = Path(__file__).parent / "specs" / "ora004"


class SpecOra004(TypedDict):
    regra: RegraOra004Spec
    descoberta: dict[str, Any]


def _carregar_arquivo(caminho: Path) -> SpecOra004:
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    if "regra" not in bruto or "descoberta" not in bruto:
        raise SpecInvalido(f"{caminho.name}: esperava as chaves 'regra' e 'descoberta'")
    return SpecOra004(
        regra=RegraOra004Spec.model_validate(bruto["regra"]), descoberta=bruto["descoberta"]
    )


def carregar_especificacoes_ora004() -> list[SpecOra004]:
    return [_carregar_arquivo(caminho) for caminho in sorted(_DIR_SPECS.glob("*.json"))]
