"""Loader do spec bespoke DOC-004 (`specs/doc004/*.json`) — mesmo padrão
de `a11y003_loader.py`: só 1 código, não generalizado em Skill."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from batman_os.capabilities.rules.doc004_changelog_sem_versao import RegraDoc004Spec
from batman_os.capabilities.rules.lote_01 import SpecInvalido

_DIR_SPECS = Path(__file__).parent / "specs" / "doc004"


class SpecDoc004(TypedDict):
    regra: RegraDoc004Spec
    descoberta: dict[str, Any]


def _carregar_arquivo(caminho: Path) -> SpecDoc004:
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    if "regra" not in bruto or "descoberta" not in bruto:
        raise SpecInvalido(f"{caminho.name}: esperava as chaves 'regra' e 'descoberta'")
    return SpecDoc004(
        regra=RegraDoc004Spec.model_validate(bruto["regra"]), descoberta=bruto["descoberta"]
    )


def carregar_especificacoes_doc004() -> list[SpecDoc004]:
    return [_carregar_arquivo(caminho) for caminho in sorted(_DIR_SPECS.glob("*.json"))]
