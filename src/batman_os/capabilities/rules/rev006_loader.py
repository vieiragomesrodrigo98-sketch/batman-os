"""Loader do spec bespoke REV-006 (`specs/rev006/*.json`) — mesmo padrão
de `a11y003_loader.py`: só 1 código, não generalizado em Skill."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from batman_os.capabilities.rules.lote_01 import SpecInvalido
from batman_os.capabilities.rules.rev006_variavel_nome_curto import RegraRev006Spec

_DIR_SPECS = Path(__file__).parent / "specs" / "rev006"


class SpecRev006(TypedDict):
    regra: RegraRev006Spec
    descoberta: dict[str, Any]


def _carregar_arquivo(caminho: Path) -> SpecRev006:
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    if "regra" not in bruto or "descoberta" not in bruto:
        raise SpecInvalido(f"{caminho.name}: esperava as chaves 'regra' e 'descoberta'")
    return SpecRev006(
        regra=RegraRev006Spec.model_validate(bruto["regra"]), descoberta=bruto["descoberta"]
    )


def carregar_especificacoes_rev006() -> list[SpecRev006]:
    return [_carregar_arquivo(caminho) for caminho in sorted(_DIR_SPECS.glob("*.json"))]
