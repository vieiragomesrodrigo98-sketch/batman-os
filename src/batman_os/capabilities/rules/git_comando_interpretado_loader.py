"""Loader dos specs da Skill "comando git único interpretado"
(`specs/git_comando_interpretado/*.json`) — Milestone 3, Skill 3.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from batman_os.capabilities.rules.git_comando_interpretado import RegraComparacaoNumericaSpec
from batman_os.capabilities.rules.lote_01 import SpecInvalido

_DIR_SPECS = Path(__file__).parent / "specs" / "git_comando_interpretado"


class SpecDeRegraGitInterpretado(TypedDict):
    regra: RegraComparacaoNumericaSpec
    descoberta: dict[str, Any]


def _carregar_arquivo(caminho: Path) -> SpecDeRegraGitInterpretado:
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    if "regra" not in bruto or "descoberta" not in bruto:
        raise SpecInvalido(f"{caminho.name}: esperava as chaves 'regra' e 'descoberta'")
    return SpecDeRegraGitInterpretado(
        regra=RegraComparacaoNumericaSpec.model_validate(bruto["regra"]),
        descoberta=bruto["descoberta"],
    )


def carregar_especificacoes_git_interpretado() -> list[SpecDeRegraGitInterpretado]:
    return [_carregar_arquivo(caminho) for caminho in sorted(_DIR_SPECS.glob("*.json"))]
