"""Loader do spec bespoke A11Y-002 (`specs/a11y002/*.json`) — mesmo
padrão de `a11y003_loader.py`: só 1 código, não generalizado em Skill."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from batman_os.capabilities.rules.a11y002_onclick_sem_teclado import RegraA11y002Spec
from batman_os.capabilities.rules.lote_01 import SpecInvalido

_DIR_SPECS = Path(__file__).parent / "specs" / "a11y002"


class SpecA11y002(TypedDict):
    regra: RegraA11y002Spec
    descoberta: dict[str, Any]


def _carregar_arquivo(caminho: Path) -> SpecA11y002:
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    if "regra" not in bruto or "descoberta" not in bruto:
        raise SpecInvalido(f"{caminho.name}: esperava as chaves 'regra' e 'descoberta'")
    return SpecA11y002(
        regra=RegraA11y002Spec.model_validate(bruto["regra"]), descoberta=bruto["descoberta"]
    )


def carregar_especificacoes_a11y002() -> list[SpecA11y002]:
    return [_carregar_arquivo(caminho) for caminho in sorted(_DIR_SPECS.glob("*.json"))]
