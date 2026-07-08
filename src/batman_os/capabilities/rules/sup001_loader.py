"""Loader do spec bespoke SUP-001 (`specs/sup001/*.json`) — mesmo padrão
de `de003_loader.py`: só 1 código, não generalizado em Skill."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from batman_os.capabilities.rules.lote_01 import SpecInvalido
from batman_os.capabilities.rules.sup001_excecao_silenciada import RegraSup001Spec

_DIR_SPECS = Path(__file__).parent / "specs" / "sup001"


class SpecSup001(TypedDict):
    regra: RegraSup001Spec
    descoberta: dict[str, Any]


def _carregar_arquivo(caminho: Path) -> SpecSup001:
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    if "regra" not in bruto or "descoberta" not in bruto:
        raise SpecInvalido(f"{caminho.name}: esperava as chaves 'regra' e 'descoberta'")
    return SpecSup001(
        regra=RegraSup001Spec.model_validate(bruto["regra"]), descoberta=bruto["descoberta"]
    )


def carregar_especificacoes_sup001() -> list[SpecSup001]:
    return [_carregar_arquivo(caminho) for caminho in sorted(_DIR_SPECS.glob("*.json"))]
