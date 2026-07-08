"""Loader do spec bespoke BA-004 (`specs/ba004/*.json`) — mesmo padrão de
`be013_loader.py`: só 1 código, não generalizado em Skill."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from batman_os.capabilities.rules.ba004_logica_negocio_router import RegraBa004Spec
from batman_os.capabilities.rules.lote_01 import SpecInvalido

_DIR_SPECS = Path(__file__).parent / "specs" / "ba004"


class SpecBa004(TypedDict):
    regra: RegraBa004Spec
    descoberta: dict[str, Any]


def _carregar_arquivo(caminho: Path) -> SpecBa004:
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    if "regra" not in bruto or "descoberta" not in bruto:
        raise SpecInvalido(f"{caminho.name}: esperava as chaves 'regra' e 'descoberta'")
    return SpecBa004(
        regra=RegraBa004Spec.model_validate(bruto["regra"]), descoberta=bruto["descoberta"]
    )


def carregar_especificacoes_ba004() -> list[SpecBa004]:
    return [_carregar_arquivo(caminho) for caminho in sorted(_DIR_SPECS.glob("*.json"))]
