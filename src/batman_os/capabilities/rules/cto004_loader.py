"""Loader do spec bespoke CTO-004 (`specs/cto004/*.json`) — mesmo padrão
de `a11y003_loader.py`: só 1 código, não generalizado em Skill."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from batman_os.capabilities.rules.cto004_endpoint_sem_doc import RegraCto004Spec
from batman_os.capabilities.rules.lote_01 import SpecInvalido

_DIR_SPECS = Path(__file__).parent / "specs" / "cto004"


class SpecCto004(TypedDict):
    regra: RegraCto004Spec
    descoberta: dict[str, Any]


def _carregar_arquivo(caminho: Path) -> SpecCto004:
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    if "regra" not in bruto or "descoberta" not in bruto:
        raise SpecInvalido(f"{caminho.name}: esperava as chaves 'regra' e 'descoberta'")
    return SpecCto004(
        regra=RegraCto004Spec.model_validate(bruto["regra"]), descoberta=bruto["descoberta"]
    )


def carregar_especificacoes_cto004() -> list[SpecCto004]:
    return [_carregar_arquivo(caminho) for caminho in sorted(_DIR_SPECS.glob("*.json"))]
