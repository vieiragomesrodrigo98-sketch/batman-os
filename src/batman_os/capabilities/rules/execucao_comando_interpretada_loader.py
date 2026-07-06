"""Loader dos specs da Skill "executar comando externo, timeout, venv-aware"
(`specs/execucao_comando_interpretada/*.json`) — Milestone 3, Skill 4.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from batman_os.capabilities.rules.execucao_comando_interpretada import (
    RegraExecucaoComandoSpec,
)
from batman_os.capabilities.rules.lote_01 import SpecInvalido

_DIR_SPECS = Path(__file__).parent / "specs" / "execucao_comando_interpretada"


class SpecDeRegraExecucaoComando(TypedDict):
    regra: RegraExecucaoComandoSpec
    descoberta: dict[str, Any]


def _carregar_arquivo(caminho: Path) -> SpecDeRegraExecucaoComando:
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    if "regra" not in bruto or "descoberta" not in bruto:
        raise SpecInvalido(f"{caminho.name}: esperava as chaves 'regra' e 'descoberta'")
    return SpecDeRegraExecucaoComando(
        regra=RegraExecucaoComandoSpec.model_validate(bruto["regra"]),
        descoberta=bruto["descoberta"],
    )


def carregar_especificacoes_execucao_comando() -> list[SpecDeRegraExecucaoComando]:
    return [_carregar_arquivo(caminho) for caminho in sorted(_DIR_SPECS.glob("*.json"))]
