"""Loader dos specs da Skill AST "nó selecionado sem padrão no corpo/
contexto" (`specs/ast_padrao_ausente/*.json`) — Milestone 3. Mesmo padrão de
`lote_01.py`/`lote_02.py`, mas `regra` valida contra `RegraAstSpec`
(`ast_padrao_ausente.py`), não `RegraSpec`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from batman_os.capabilities.rules.ast_padrao_ausente import RegraAstSpec
from batman_os.capabilities.rules.lote_01 import SpecInvalido

_DIR_SPECS = Path(__file__).parent / "specs" / "ast_padrao_ausente"


class SpecDeRegraAst(TypedDict):
    regra: RegraAstSpec
    descoberta: dict[str, Any]


def _carregar_arquivo(caminho: Path) -> SpecDeRegraAst:
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    if "regra" not in bruto or "descoberta" not in bruto:
        raise SpecInvalido(f"{caminho.name}: esperava as chaves 'regra' e 'descoberta'")
    return SpecDeRegraAst(
        regra=RegraAstSpec.model_validate(bruto["regra"]), descoberta=bruto["descoberta"]
    )


def carregar_especificacoes_ast() -> list[SpecDeRegraAst]:
    return [_carregar_arquivo(caminho) for caminho in sorted(_DIR_SPECS.glob("*.json"))]
