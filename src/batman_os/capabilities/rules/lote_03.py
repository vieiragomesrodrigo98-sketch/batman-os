"""Loader do terceiro lote de migração (`specs/lote_03/*.json`) — continuação
da migração do Batman atual além do escopo original de Milestones 1-3
(código já existia via `regex_sobre_conteudo`, só specs novos). Mesmo padrão
de `lote_01.py`/`lote_02.py`.
"""

from __future__ import annotations

import json
from pathlib import Path

from batman_os.capabilities.rules.lote_01 import SpecDeRegra, SpecInvalido
from batman_os.capabilities.rules.regex_sobre_conteudo import RegraSpec

_DIR_SPECS = Path(__file__).parent / "specs" / "lote_03"


def _carregar_arquivo(caminho: Path) -> SpecDeRegra:
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    if "regra" not in bruto or "descoberta" not in bruto:
        raise SpecInvalido(f"{caminho.name}: esperava as chaves 'regra' e 'descoberta'")
    return SpecDeRegra(
        regra=RegraSpec.model_validate(bruto["regra"]), descoberta=bruto["descoberta"]
    )


def carregar_lote_03() -> list[SpecDeRegra]:
    """Carrega os specs do terceiro lote, ordenados por nome de arquivo."""
    return [_carregar_arquivo(caminho) for caminho in sorted(_DIR_SPECS.glob("*.json"))]
