"""Loader do spec bespoke FE-API (`specs/feapi/*.json`) — mesmo padrão de
`arch003_loader.py`: só 1 código, não generalizado em Skill."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from batman_os.capabilities.rules.feapi_rota_sem_frontend import RegraFeApiSpec
from batman_os.capabilities.rules.lote_01 import SpecInvalido

_DIR_SPECS = Path(__file__).parent / "specs" / "feapi"


class SpecFeApi(TypedDict):
    regra: RegraFeApiSpec
    descoberta: dict[str, Any]


def _carregar_arquivo(caminho: Path) -> SpecFeApi:
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    if "regra" not in bruto or "descoberta" not in bruto:
        raise SpecInvalido(f"{caminho.name}: esperava as chaves 'regra' e 'descoberta'")
    return SpecFeApi(
        regra=RegraFeApiSpec.model_validate(bruto["regra"]), descoberta=bruto["descoberta"]
    )


def carregar_especificacoes_feapi() -> list[SpecFeApi]:
    return [_carregar_arquivo(caminho) for caminho in sorted(_DIR_SPECS.glob("*.json"))]
