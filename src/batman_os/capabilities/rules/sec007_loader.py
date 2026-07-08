"""Loader do spec bespoke SEC-007 (`specs/sec007/*.json`) — mesmo padrão
de `sec005_loader.py`: só 1 código, não generalizado em Skill."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from batman_os.capabilities.rules.lote_01 import SpecInvalido
from batman_os.capabilities.rules.sec007_ddl_no_import import RegraSec007Spec

_DIR_SPECS = Path(__file__).parent / "specs" / "sec007"


class SpecSec007(TypedDict):
    regra: RegraSec007Spec
    descoberta: dict[str, Any]


def _carregar_arquivo(caminho: Path) -> SpecSec007:
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    if "regra" not in bruto or "descoberta" not in bruto:
        raise SpecInvalido(f"{caminho.name}: esperava as chaves 'regra' e 'descoberta'")
    return SpecSec007(
        regra=RegraSec007Spec.model_validate(bruto["regra"]), descoberta=bruto["descoberta"]
    )


def carregar_especificacoes_sec007() -> list[SpecSec007]:
    return [_carregar_arquivo(caminho) for caminho in sorted(_DIR_SPECS.glob("*.json"))]
