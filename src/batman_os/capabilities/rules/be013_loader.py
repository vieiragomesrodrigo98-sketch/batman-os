"""Loader do spec bespoke BE-013 (`specs/be013/*.json`) — mesmo padrão de
`sec007_loader.py`: só 1 código, não generalizado em Skill."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from batman_os.capabilities.rules.be013_http200_em_except import RegraBe013Spec
from batman_os.capabilities.rules.lote_01 import SpecInvalido

_DIR_SPECS = Path(__file__).parent / "specs" / "be013"


class SpecBe013(TypedDict):
    regra: RegraBe013Spec
    descoberta: dict[str, Any]


def _carregar_arquivo(caminho: Path) -> SpecBe013:
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    if "regra" not in bruto or "descoberta" not in bruto:
        raise SpecInvalido(f"{caminho.name}: esperava as chaves 'regra' e 'descoberta'")
    return SpecBe013(
        regra=RegraBe013Spec.model_validate(bruto["regra"]), descoberta=bruto["descoberta"]
    )


def carregar_especificacoes_be013() -> list[SpecBe013]:
    return [_carregar_arquivo(caminho) for caminho in sorted(_DIR_SPECS.glob("*.json"))]
