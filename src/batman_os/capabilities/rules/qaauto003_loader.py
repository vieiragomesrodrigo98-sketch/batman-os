"""Loader do spec bespoke QA-AUTO-003 (`specs/qaauto003/*.json`) — mesmo
padrão de `a11y003_loader.py`: só 1 código, não generalizado em Skill."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from batman_os.capabilities.rules.lote_01 import SpecInvalido
from batman_os.capabilities.rules.qaauto003_smoke_specs_ausentes import RegraQaAuto003Spec

_DIR_SPECS = Path(__file__).parent / "specs" / "qaauto003"


class SpecQaAuto003(TypedDict):
    regra: RegraQaAuto003Spec
    descoberta: dict[str, Any]


def _carregar_arquivo(caminho: Path) -> SpecQaAuto003:
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    if "regra" not in bruto or "descoberta" not in bruto:
        raise SpecInvalido(f"{caminho.name}: esperava as chaves 'regra' e 'descoberta'")
    return SpecQaAuto003(
        regra=RegraQaAuto003Spec.model_validate(bruto["regra"]), descoberta=bruto["descoberta"]
    )


def carregar_especificacoes_qaauto003() -> list[SpecQaAuto003]:
    return [_carregar_arquivo(caminho) for caminho in sorted(_DIR_SPECS.glob("*.json"))]
