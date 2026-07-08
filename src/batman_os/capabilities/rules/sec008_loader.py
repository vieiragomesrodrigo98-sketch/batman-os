"""Loader do spec bespoke SEC-008 (`specs/sec008/*.json`) — mesmo padrão
de `a11y003_loader.py`: só 1 código, não generalizado em Skill."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from batman_os.capabilities.rules.lote_01 import SpecInvalido
from batman_os.capabilities.rules.sec008_role_sem_super_admin import RegraSec008Spec

_DIR_SPECS = Path(__file__).parent / "specs" / "sec008"


class SpecSec008(TypedDict):
    regra: RegraSec008Spec
    descoberta: dict[str, Any]


def _carregar_arquivo(caminho: Path) -> SpecSec008:
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    if "regra" not in bruto or "descoberta" not in bruto:
        raise SpecInvalido(f"{caminho.name}: esperava as chaves 'regra' e 'descoberta'")
    return SpecSec008(
        regra=RegraSec008Spec.model_validate(bruto["regra"]), descoberta=bruto["descoberta"]
    )


def carregar_especificacoes_sec008() -> list[SpecSec008]:
    return [_carregar_arquivo(caminho) for caminho in sorted(_DIR_SPECS.glob("*.json"))]
