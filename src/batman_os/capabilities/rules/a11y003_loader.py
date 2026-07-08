"""Loader do spec bespoke A11Y-003 (`specs/a11y003/*.json`) — mesmo
padrão de `fe001_loader.py`: só 1 código, não generalizado em Skill."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from batman_os.capabilities.rules.a11y003_input_sem_label import RegraA11y003Spec
from batman_os.capabilities.rules.lote_01 import SpecInvalido

_DIR_SPECS = Path(__file__).parent / "specs" / "a11y003"


class SpecA11y003(TypedDict):
    regra: RegraA11y003Spec
    descoberta: dict[str, Any]


def _carregar_arquivo(caminho: Path) -> SpecA11y003:
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    if "regra" not in bruto or "descoberta" not in bruto:
        raise SpecInvalido(f"{caminho.name}: esperava as chaves 'regra' e 'descoberta'")
    return SpecA11y003(
        regra=RegraA11y003Spec.model_validate(bruto["regra"]), descoberta=bruto["descoberta"]
    )


def carregar_especificacoes_a11y003() -> list[SpecA11y003]:
    return [_carregar_arquivo(caminho) for caminho in sorted(_DIR_SPECS.glob("*.json"))]
