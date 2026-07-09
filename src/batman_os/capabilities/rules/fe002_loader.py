"""Loader do spec bespoke FE-002 (`specs/fe002/*.json`) — mesmo padrão de
`a11y003_loader.py`: só 1 código, não generalizado em Skill."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from batman_os.capabilities.rules.fe002_tofixed_sem_null_safety import RegraFe002Spec
from batman_os.capabilities.rules.lote_01 import SpecInvalido

_DIR_SPECS = Path(__file__).parent / "specs" / "fe002"


class SpecFe002(TypedDict):
    regra: RegraFe002Spec
    descoberta: dict[str, Any]


def _carregar_arquivo(caminho: Path) -> SpecFe002:
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    if "regra" not in bruto or "descoberta" not in bruto:
        raise SpecInvalido(f"{caminho.name}: esperava as chaves 'regra' e 'descoberta'")
    return SpecFe002(
        regra=RegraFe002Spec.model_validate(bruto["regra"]), descoberta=bruto["descoberta"]
    )


def carregar_especificacoes_fe002() -> list[SpecFe002]:
    return [_carregar_arquivo(caminho) for caminho in sorted(_DIR_SPECS.glob("*.json"))]
