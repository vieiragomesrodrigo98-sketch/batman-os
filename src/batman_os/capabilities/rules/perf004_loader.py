"""Loader do spec bespoke PERF-004 (`specs/perf004/*.json`) — mesmo
padrão de `a11y003_loader.py`: só 1 código, não generalizado em Skill."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from batman_os.capabilities.rules.lote_01 import SpecInvalido
from batman_os.capabilities.rules.perf004_arquivo_sem_streaming import RegraPerf004Spec

_DIR_SPECS = Path(__file__).parent / "specs" / "perf004"


class SpecPerf004(TypedDict):
    regra: RegraPerf004Spec
    descoberta: dict[str, Any]


def _carregar_arquivo(caminho: Path) -> SpecPerf004:
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    if "regra" not in bruto or "descoberta" not in bruto:
        raise SpecInvalido(f"{caminho.name}: esperava as chaves 'regra' e 'descoberta'")
    return SpecPerf004(
        regra=RegraPerf004Spec.model_validate(bruto["regra"]), descoberta=bruto["descoberta"]
    )


def carregar_especificacoes_perf004() -> list[SpecPerf004]:
    return [_carregar_arquivo(caminho) for caminho in sorted(_DIR_SPECS.glob("*.json"))]
