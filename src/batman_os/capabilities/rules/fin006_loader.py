"""Loader do spec bespoke FIN-006 (`specs/fin006/*.json`) — mesmo padrão
de `fin005_loader.py`/`ora005_loader.py`: só 1 código."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from batman_os.capabilities.rules.fin006_significancia_sem_cluster import RegraFin006Spec
from batman_os.capabilities.rules.lote_01 import SpecInvalido

_DIR_SPECS = Path(__file__).parent / "specs" / "fin006"


class SpecFin006(TypedDict):
    regra: RegraFin006Spec
    descoberta: dict[str, Any]


def _carregar_arquivo(caminho: Path) -> SpecFin006:
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    if "regra" not in bruto or "descoberta" not in bruto:
        raise SpecInvalido(f"{caminho.name}: esperava as chaves 'regra' e 'descoberta'")
    return SpecFin006(
        regra=RegraFin006Spec.model_validate(bruto["regra"]), descoberta=bruto["descoberta"]
    )


def carregar_especificacoes_fin006() -> list[SpecFin006]:
    return [_carregar_arquivo(caminho) for caminho in sorted(_DIR_SPECS.glob("*.json"))]
