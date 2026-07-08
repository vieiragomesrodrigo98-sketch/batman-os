"""Loader do spec bespoke FE-001 (`specs/fe001/*.json`) — mesmo padrão de
`feapi_loader.py`: só 1 código, não generalizado em Skill."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from batman_os.capabilities.rules.fe001_export_duplicado import RegraFe001Spec
from batman_os.capabilities.rules.lote_01 import SpecInvalido

_DIR_SPECS = Path(__file__).parent / "specs" / "fe001"


class SpecFe001(TypedDict):
    regra: RegraFe001Spec
    descoberta: dict[str, Any]


def _carregar_arquivo(caminho: Path) -> SpecFe001:
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    if "regra" not in bruto or "descoberta" not in bruto:
        raise SpecInvalido(f"{caminho.name}: esperava as chaves 'regra' e 'descoberta'")
    return SpecFe001(
        regra=RegraFe001Spec.model_validate(bruto["regra"]), descoberta=bruto["descoberta"]
    )


def carregar_especificacoes_fe001() -> list[SpecFe001]:
    return [_carregar_arquivo(caminho) for caminho in sorted(_DIR_SPECS.glob("*.json"))]
