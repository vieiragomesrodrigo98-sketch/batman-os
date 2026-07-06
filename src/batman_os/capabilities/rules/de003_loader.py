"""Loader do spec bespoke DE-003 (`specs/de003/*.json`) — Milestone 3,
Skill 6. Mesmo padrão de `lote_01.py`, mas só 1 código (não generalizado
em Skill)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from batman_os.capabilities.rules.de003_coluna_sem_migration import RegraDe003Spec
from batman_os.capabilities.rules.lote_01 import SpecInvalido

_DIR_SPECS = Path(__file__).parent / "specs" / "de003"


class SpecDe003(TypedDict):
    regra: RegraDe003Spec
    descoberta: dict[str, Any]


def _carregar_arquivo(caminho: Path) -> SpecDe003:
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    if "regra" not in bruto or "descoberta" not in bruto:
        raise SpecInvalido(f"{caminho.name}: esperava as chaves 'regra' e 'descoberta'")
    return SpecDe003(
        regra=RegraDe003Spec.model_validate(bruto["regra"]), descoberta=bruto["descoberta"]
    )


def carregar_especificacoes_de003() -> list[SpecDe003]:
    return [_carregar_arquivo(caminho) for caminho in sorted(_DIR_SPECS.glob("*.json"))]
