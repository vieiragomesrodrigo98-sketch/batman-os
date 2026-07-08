"""Loader do spec bespoke PD-011 (`specs/pd011/*.json`) — mesmo padrão de
`fe001_loader.py`: só 1 código, não generalizado em Skill."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from batman_os.capabilities.rules.lote_01 import SpecInvalido
from batman_os.capabilities.rules.pd011_diversificacao_nao_comunicada import RegraPd011Spec

_DIR_SPECS = Path(__file__).parent / "specs" / "pd011"


class SpecPd011(TypedDict):
    regra: RegraPd011Spec
    descoberta: dict[str, Any]


def _carregar_arquivo(caminho: Path) -> SpecPd011:
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    if "regra" not in bruto or "descoberta" not in bruto:
        raise SpecInvalido(f"{caminho.name}: esperava as chaves 'regra' e 'descoberta'")
    return SpecPd011(
        regra=RegraPd011Spec.model_validate(bruto["regra"]), descoberta=bruto["descoberta"]
    )


def carregar_especificacoes_pd011() -> list[SpecPd011]:
    return [_carregar_arquivo(caminho) for caminho in sorted(_DIR_SPECS.glob("*.json"))]
