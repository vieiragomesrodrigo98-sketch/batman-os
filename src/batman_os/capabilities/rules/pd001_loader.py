"""Loader do spec bespoke PD-001 (`specs/pd001/*.json`) — mesmo padrão de
`a11y003_loader.py`: só 1 código, não generalizado em Skill."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from batman_os.capabilities.rules.lote_01 import SpecInvalido
from batman_os.capabilities.rules.pd001_empty_state_sem_cta import RegraPd001Spec

_DIR_SPECS = Path(__file__).parent / "specs" / "pd001"


class SpecPd001(TypedDict):
    regra: RegraPd001Spec
    descoberta: dict[str, Any]


def _carregar_arquivo(caminho: Path) -> SpecPd001:
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    if "regra" not in bruto or "descoberta" not in bruto:
        raise SpecInvalido(f"{caminho.name}: esperava as chaves 'regra' e 'descoberta'")
    return SpecPd001(
        regra=RegraPd001Spec.model_validate(bruto["regra"]), descoberta=bruto["descoberta"]
    )


def carregar_especificacoes_pd001() -> list[SpecPd001]:
    return [_carregar_arquivo(caminho) for caminho in sorted(_DIR_SPECS.glob("*.json"))]
