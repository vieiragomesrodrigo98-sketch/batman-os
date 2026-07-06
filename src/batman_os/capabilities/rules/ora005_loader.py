"""Loader do spec bespoke ORA-005 (`specs/ora005/*.json`) — Milestone 3,
Skill 6. Mesmo padrão de `de003_loader.py` — só 1 código."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from batman_os.capabilities.rules.lote_01 import SpecInvalido
from batman_os.capabilities.rules.ora005_fallback_silencioso import RegraOra005Spec

_DIR_SPECS = Path(__file__).parent / "specs" / "ora005"


class SpecOra005(TypedDict):
    regra: RegraOra005Spec
    descoberta: dict[str, Any]


def _carregar_arquivo(caminho: Path) -> SpecOra005:
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    if "regra" not in bruto or "descoberta" not in bruto:
        raise SpecInvalido(f"{caminho.name}: esperava as chaves 'regra' e 'descoberta'")
    return SpecOra005(
        regra=RegraOra005Spec.model_validate(bruto["regra"]), descoberta=bruto["descoberta"]
    )


def carregar_especificacoes_ora005() -> list[SpecOra005]:
    return [_carregar_arquivo(caminho) for caminho in sorted(_DIR_SPECS.glob("*.json"))]
