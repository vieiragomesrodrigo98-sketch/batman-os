"""Loader do spec bespoke CTO-002 (`specs/cto002/*.json`) — mesmo padrão
de `a11y003_loader.py`: só 1 código, não generalizado em Skill."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from batman_os.capabilities.rules.cto002_rota_sem_versao import RegraCto002Spec
from batman_os.capabilities.rules.lote_01 import SpecInvalido

_DIR_SPECS = Path(__file__).parent / "specs" / "cto002"


class SpecCto002(TypedDict):
    regra: RegraCto002Spec
    descoberta: dict[str, Any]


def _carregar_arquivo(caminho: Path) -> SpecCto002:
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    if "regra" not in bruto or "descoberta" not in bruto:
        raise SpecInvalido(f"{caminho.name}: esperava as chaves 'regra' e 'descoberta'")
    return SpecCto002(
        regra=RegraCto002Spec.model_validate(bruto["regra"]), descoberta=bruto["descoberta"]
    )


def carregar_especificacoes_cto002() -> list[SpecCto002]:
    return [_carregar_arquivo(caminho) for caminho in sorted(_DIR_SPECS.glob("*.json"))]
