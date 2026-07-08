"""Loader do spec bespoke PD-009 (`specs/pd009/*.json`) — mesmo padrão de
`a11y003_loader.py`: só 1 código, não generalizado em Skill."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from batman_os.capabilities.rules.lote_01 import SpecInvalido
from batman_os.capabilities.rules.pd009_rota_nao_descobrivel import RegraPd009Spec

_DIR_SPECS = Path(__file__).parent / "specs" / "pd009"


class SpecPd009(TypedDict):
    regra: RegraPd009Spec
    descoberta: dict[str, Any]


def _carregar_arquivo(caminho: Path) -> SpecPd009:
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    if "regra" not in bruto or "descoberta" not in bruto:
        raise SpecInvalido(f"{caminho.name}: esperava as chaves 'regra' e 'descoberta'")
    return SpecPd009(
        regra=RegraPd009Spec.model_validate(bruto["regra"]), descoberta=bruto["descoberta"]
    )


def carregar_especificacoes_pd009() -> list[SpecPd009]:
    return [_carregar_arquivo(caminho) for caminho in sorted(_DIR_SPECS.glob("*.json"))]
