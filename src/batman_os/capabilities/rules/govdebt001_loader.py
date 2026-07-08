"""Loader do spec bespoke GOVDEBT-001 (`specs/govdebt001/*.json`) —
mesmo padrão de `a11y003_loader.py`: só 1 código, não generalizado em
Skill."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from batman_os.capabilities.rules.govdebt001_finding_sem_decisao import RegraGovdebt001Spec
from batman_os.capabilities.rules.lote_01 import SpecInvalido

_DIR_SPECS = Path(__file__).parent / "specs" / "govdebt001"


class SpecGovdebt001(TypedDict):
    regra: RegraGovdebt001Spec
    descoberta: dict[str, Any]


def _carregar_arquivo(caminho: Path) -> SpecGovdebt001:
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    if "regra" not in bruto or "descoberta" not in bruto:
        raise SpecInvalido(f"{caminho.name}: esperava as chaves 'regra' e 'descoberta'")
    return SpecGovdebt001(
        regra=RegraGovdebt001Spec.model_validate(bruto["regra"]), descoberta=bruto["descoberta"]
    )


def carregar_especificacoes_govdebt001() -> list[SpecGovdebt001]:
    return [_carregar_arquivo(caminho) for caminho in sorted(_DIR_SPECS.glob("*.json"))]
