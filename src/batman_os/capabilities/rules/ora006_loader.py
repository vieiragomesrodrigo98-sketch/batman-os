"""Loader do spec bespoke ORA-006 (`specs/ora006/*.json`) — mesmo padrão
de `ora005_loader.py`: só 1 código."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from batman_os.capabilities.rules.lote_01 import SpecInvalido
from batman_os.capabilities.rules.ora006_proxy_medicao_silenciosa import RegraOra006Spec

_DIR_SPECS = Path(__file__).parent / "specs" / "ora006"


class SpecOra006(TypedDict):
    regra: RegraOra006Spec
    descoberta: dict[str, Any]


def _carregar_arquivo(caminho: Path) -> SpecOra006:
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    if "regra" not in bruto or "descoberta" not in bruto:
        raise SpecInvalido(f"{caminho.name}: esperava as chaves 'regra' e 'descoberta'")
    return SpecOra006(
        regra=RegraOra006Spec.model_validate(bruto["regra"]), descoberta=bruto["descoberta"]
    )


def carregar_especificacoes_ora006() -> list[SpecOra006]:
    return [_carregar_arquivo(caminho) for caminho in sorted(_DIR_SPECS.glob("*.json"))]
