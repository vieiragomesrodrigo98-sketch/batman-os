"""Loader do spec bespoke PD-010 (`specs/pd010/*.json`) — mesmo padrão de
`a11y003_loader.py`: só 1 código, não generalizado em Skill."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from batman_os.capabilities.rules.lote_01 import SpecInvalido
from batman_os.capabilities.rules.pd010_simulador_sem_piso import RegraPd010Spec

_DIR_SPECS = Path(__file__).parent / "specs" / "pd010"


class SpecPd010(TypedDict):
    regra: RegraPd010Spec
    descoberta: dict[str, Any]


def _carregar_arquivo(caminho: Path) -> SpecPd010:
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    if "regra" not in bruto or "descoberta" not in bruto:
        raise SpecInvalido(f"{caminho.name}: esperava as chaves 'regra' e 'descoberta'")
    return SpecPd010(
        regra=RegraPd010Spec.model_validate(bruto["regra"]), descoberta=bruto["descoberta"]
    )


def carregar_especificacoes_pd010() -> list[SpecPd010]:
    return [_carregar_arquivo(caminho) for caminho in sorted(_DIR_SPECS.glob("*.json"))]
