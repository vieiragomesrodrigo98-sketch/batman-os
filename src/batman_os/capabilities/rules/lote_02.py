"""Loader do segundo lote de migração (`specs/lote_02/*.json`) — Milestone 2:
migração mecânica em massa das regras restantes de regex/substring/
existência de arquivo do Batman atual. Mesmo padrão de `lote_01.py`.
"""

from __future__ import annotations

import json
from pathlib import Path

from batman_os.capabilities.rules.lote_01 import SpecDeRegra, SpecInvalido
from batman_os.capabilities.rules.regex_sobre_conteudo import RegraSpec

_DIR_SPECS = Path(__file__).parent / "specs" / "lote_02"


def _carregar_arquivo(caminho: Path) -> SpecDeRegra:
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    if "regra" not in bruto or "descoberta" not in bruto:
        raise SpecInvalido(f"{caminho.name}: esperava as chaves 'regra' e 'descoberta'")
    return SpecDeRegra(
        regra=RegraSpec.model_validate(bruto["regra"]), descoberta=bruto["descoberta"]
    )


def carregar_lote_02() -> list[SpecDeRegra]:
    """Carrega os specs do segundo lote, ordenados por nome de arquivo
    (== código da regra)."""
    return [_carregar_arquivo(caminho) for caminho in sorted(_DIR_SPECS.glob("*.json"))]
