"""Loader do spec bespoke BA-005 (`specs/ba005/*.json`) — mesmo padrão de
`ba004_loader.py`: só 1 código, não generalizado em Skill."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from batman_os.capabilities.rules.ba005_divisao_sem_guarda import RegraBa005Spec
from batman_os.capabilities.rules.lote_01 import SpecInvalido

_DIR_SPECS = Path(__file__).parent / "specs" / "ba005"


class SpecBa005(TypedDict):
    regra: RegraBa005Spec
    descoberta: dict[str, Any]


def _carregar_arquivo(caminho: Path) -> SpecBa005:
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    if "regra" not in bruto or "descoberta" not in bruto:
        raise SpecInvalido(f"{caminho.name}: esperava as chaves 'regra' e 'descoberta'")
    return SpecBa005(
        regra=RegraBa005Spec.model_validate(bruto["regra"]), descoberta=bruto["descoberta"]
    )


def carregar_especificacoes_ba005() -> list[SpecBa005]:
    return [_carregar_arquivo(caminho) for caminho in sorted(_DIR_SPECS.glob("*.json"))]
