"""Loader do spec bespoke QA-AUTO-001 (`specs/qaauto001/*.json`) — mesmo
padrão de `fe001_loader.py`: só 1 código, não generalizado em Skill."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from batman_os.capabilities.rules.lote_01 import SpecInvalido
from batman_os.capabilities.rules.qaauto001_router_sem_teste import RegraQaAuto001Spec

_DIR_SPECS = Path(__file__).parent / "specs" / "qaauto001"


class SpecQaAuto001(TypedDict):
    regra: RegraQaAuto001Spec
    descoberta: dict[str, Any]


def _carregar_arquivo(caminho: Path) -> SpecQaAuto001:
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    if "regra" not in bruto or "descoberta" not in bruto:
        raise SpecInvalido(f"{caminho.name}: esperava as chaves 'regra' e 'descoberta'")
    return SpecQaAuto001(
        regra=RegraQaAuto001Spec.model_validate(bruto["regra"]), descoberta=bruto["descoberta"]
    )


def carregar_especificacoes_qaauto001() -> list[SpecQaAuto001]:
    return [_carregar_arquivo(caminho) for caminho in sorted(_DIR_SPECS.glob("*.json"))]
