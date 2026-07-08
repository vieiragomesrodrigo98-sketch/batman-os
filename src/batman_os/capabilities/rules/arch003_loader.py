"""Loader do spec bespoke ARCH-003 (`specs/arch003/*.json`) — mesmo
padrão de `sup001_loader.py`: só 1 código, não generalizado em Skill."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from batman_os.capabilities.rules.arch003_pagina_orfa import RegraArch003Spec
from batman_os.capabilities.rules.lote_01 import SpecInvalido

_DIR_SPECS = Path(__file__).parent / "specs" / "arch003"


class SpecArch003(TypedDict):
    regra: RegraArch003Spec
    descoberta: dict[str, Any]


def _carregar_arquivo(caminho: Path) -> SpecArch003:
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    if "regra" not in bruto or "descoberta" not in bruto:
        raise SpecInvalido(f"{caminho.name}: esperava as chaves 'regra' e 'descoberta'")
    return SpecArch003(
        regra=RegraArch003Spec.model_validate(bruto["regra"]), descoberta=bruto["descoberta"]
    )


def carregar_especificacoes_arch003() -> list[SpecArch003]:
    return [_carregar_arquivo(caminho) for caminho in sorted(_DIR_SPECS.glob("*.json"))]
