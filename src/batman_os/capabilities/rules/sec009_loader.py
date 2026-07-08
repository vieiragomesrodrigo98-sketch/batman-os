"""Loader do spec bespoke SEC-009 (`specs/sec009/*.json`) — mesmo padrão
de `a11y003_loader.py`: só 1 código, não generalizado em Skill."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from batman_os.capabilities.rules.lote_01 import SpecInvalido
from batman_os.capabilities.rules.sec009_admin_role_script import RegraSec009Spec

_DIR_SPECS = Path(__file__).parent / "specs" / "sec009"


class SpecSec009(TypedDict):
    regra: RegraSec009Spec
    descoberta: dict[str, Any]


def _carregar_arquivo(caminho: Path) -> SpecSec009:
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    if "regra" not in bruto or "descoberta" not in bruto:
        raise SpecInvalido(f"{caminho.name}: esperava as chaves 'regra' e 'descoberta'")
    return SpecSec009(
        regra=RegraSec009Spec.model_validate(bruto["regra"]), descoberta=bruto["descoberta"]
    )


def carregar_especificacoes_sec009() -> list[SpecSec009]:
    return [_carregar_arquivo(caminho) for caminho in sorted(_DIR_SPECS.glob("*.json"))]
