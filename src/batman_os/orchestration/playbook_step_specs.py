"""Vol.II Cap.7/9 — construtores de entrada para steps de uma Missão
baseada em Playbook (Fase 3 do roadmap de plataforma, `.claude/plans/
peaceful-wondering-hearth.md`, Estágio 3.2).

`orchestration/playbook_driver.py` precisa saber, para cada step de um
Playbook, COMO montar sua `entrada` — a maioria dos steps não depende de
nenhum outro (uma checagem de arquivo repo-wide, `ChecagemDeArquivos`),
mas um step de relatório precisa dos `StepResult.output` de suas
dependências, só disponíveis depois delas rodarem
(`RelatorioConsolidadoSpec`).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from batman_os.foundation.types import StepId


class ConstrutorDeEntrada(Protocol):
    """Cada `PlanStepTemplate` de um Playbook precisa de um construtor
    correspondente (mesmo índice em `steps_template`) —
    `playbook_driver.py` chama `construir()` imediatamente antes de
    invocar aquele step, nunca antes."""

    def construir(self, outputs_das_dependencias: dict[StepId, Any]) -> Any: ...


@dataclass(frozen=True)
class ChecagemDeArquivos:
    """Um step de checagem repo-wide via Capability agregadora
    (`capabilities/rules/agregador_generico.py`) — ignora
    `outputs_das_dependencias` (não depende de nenhum step anterior);
    monta `itens` via uma função de descoberta JÁ EXISTENTE
    (`entradas_para_regra`/`entradas_dependencias_para_regra`,
    `cli/descoberta_arquivos.py`), reaproveitada sem alteração."""

    root: Path
    regra: Any
    descoberta: dict[str, Any]
    entradas_para_regra: Callable[[Path, Any, dict[str, Any]], list[Any]]
    capability_alvo: str

    def construir(self, outputs_das_dependencias: dict[StepId, Any]) -> Any:
        del outputs_das_dependencias
        itens = self.entradas_para_regra(self.root, self.regra, self.descoberta)
        return {
            "tipo": "agregador-generico",
            "capability_alvo": self.capability_alvo,
            "itens": [item.model_dump() for item in itens],
        }


@dataclass(frozen=True)
class RelatorioConsolidadoSpec:
    """Concatena os achados de TODAS as dependências — a peça que
    justifica o driver dedicado (`playbook_driver.py`), já que sua
    entrada só existe depois que as dependências terminam de rodar."""

    titulo_missao: str = "Auditoria de Seguranca"

    def construir(self, outputs_das_dependencias: dict[StepId, Any]) -> Any:
        achados: list[dict[str, Any]] = []
        for output in outputs_das_dependencias.values():
            achados.extend((output or {}).get("achados", []))
        return {
            "tipo": "relatorio-consolidado",
            "titulo_missao": self.titulo_missao,
            "achados": achados,
        }
