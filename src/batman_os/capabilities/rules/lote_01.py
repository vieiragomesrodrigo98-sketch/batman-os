"""Loader dos 14 specs do primeiro lote de migração (`specs/lote_01/*.json`).

Cada arquivo tem duas seções: `regra` (mapeia 1:1 para `RegraSpec` —
consumida pelo handler `avaliar_regra_regex`) e `descoberta` (interpretada
por `cli/descoberta_arquivos.py` para encontrar os arquivos no disco — não
faz parte do contrato da Capability, que é pura sobre texto já carregado).

Este módulo só lê e valida os specs; não faz nenhum IO sobre o repositório
alvo.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from batman_os.capabilities.rules.regex_sobre_conteudo import RegraSpec

_DIR_SPECS = Path(__file__).parent / "specs" / "lote_01"


class SpecDeRegra(TypedDict):
    """Um item do lote: `regra` já validada, `descoberta` como dict cru
    (formato interpretado por `cli/descoberta_arquivos.py`)."""

    regra: RegraSpec
    descoberta: dict[str, Any]


class SpecInvalido(Exception):
    """Levantada quando um arquivo em `specs/lote_01/` não tem as seções
    `regra`/`descoberta` esperadas."""


def _carregar_arquivo(caminho: Path) -> SpecDeRegra:
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    if "regra" not in bruto or "descoberta" not in bruto:
        raise SpecInvalido(f"{caminho.name}: esperava as chaves 'regra' e 'descoberta'")
    return SpecDeRegra(
        regra=RegraSpec.model_validate(bruto["regra"]), descoberta=bruto["descoberta"]
    )


def carregar_lote_01() -> list[SpecDeRegra]:
    """Carrega os 14 specs do primeiro lote, ordenados por nome de arquivo
    (== código da regra, `DEVOPS-003.json`, `RED-005.json`, etc.)."""
    return [_carregar_arquivo(caminho) for caminho in sorted(_DIR_SPECS.glob("*.json"))]
