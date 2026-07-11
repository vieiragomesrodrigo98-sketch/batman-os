"""Capability "relatório consolidado" (Vol.IV Cap.16) — Fase 3 do roadmap
de plataforma, `.claude/plans/peaceful-wondering-hearth.md`, Estágio 3.1.

Primeira Capability desta construção cuja `entrada` não é conteúdo de
arquivo, e sim uma LISTA DE ACHADOS já produzidos por outros steps de uma
Missão baseada em Playbook (`orchestration/playbook_driver.py`, Estágio
3.2, monta essa entrada a partir de `StepResult.output` das dependências).
Handler continua puro: nenhum IO, só agregação/formatação sobre dados já
recebidos.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from batman_os.capabilities.capability_contract import (
    AcceptanceTest,
    CapabilityImplementation,
    ResultadoEsperado,
)
from batman_os.capabilities.operator import ExecutionContext
from batman_os.foundation.types import CapabilityId
from batman_os.runtime.capability_engine import CapabilityDefinition, SideEffects


class EntradaRelatorioConsolidado(BaseModel):
    tipo: str = "relatorio-consolidado"
    titulo_missao: str = "Auditoria de Seguranca"
    achados: list[dict[str, Any]] = Field(default_factory=list)


class SaidaRelatorioConsolidado(BaseModel):
    titulo: str
    total_achados: int
    resumo_por_severidade: dict[str, int]
    resumo_por_codigo: dict[str, int]
    texto: str
    achados: list[dict[str, Any]]


class EntradaInvalida(Exception):
    """Levantada quando `entrada` não satisfaz `EntradaRelatorioConsolidado`
    — vira SCHEMA_REJECTION no Execution Engine (Vol.III Cap.12)."""


def _montar_texto(titulo: str, total: int, por_severidade: dict[str, int]) -> str:
    if total == 0:
        return f"{titulo}: nenhum achado."
    linhas = [f"{titulo}: {total} achado(s)."]
    for severidade in sorted(por_severidade, key=lambda s: -por_severidade[s]):
        linhas.append(f"  - {severidade}: {por_severidade[severidade]}")
    return "\n".join(linhas)


def avaliar_relatorio_consolidado(entrada: Any, contexto: ExecutionContext) -> Any:
    """Vol.IV Cap.16 — handler puro: nenhum IO, só agregação sobre achados
    já recebidos de steps anteriores."""
    del contexto
    try:
        dados = EntradaRelatorioConsolidado.model_validate(entrada)
    except Exception as exc:
        raise EntradaInvalida(str(exc)) from exc

    por_severidade: dict[str, int] = {}
    por_codigo: dict[str, int] = {}
    for achado in dados.achados:
        severidade = achado["severidade"]
        codigo = achado["codigo"]
        por_severidade[severidade] = por_severidade.get(severidade, 0) + 1
        por_codigo[codigo] = por_codigo.get(codigo, 0) + 1

    texto = _montar_texto(dados.titulo_missao, len(dados.achados), por_severidade)

    return SaidaRelatorioConsolidado(
        titulo=dados.titulo_missao,
        total_achados=len(dados.achados),
        resumo_por_severidade=por_severidade,
        resumo_por_codigo=por_codigo,
        texto=texto,
        achados=dados.achados,
    ).model_dump()


def construir_implementacao() -> CapabilityImplementation:
    """Vol.IV Cap.16, secao 16.3 — monta a `CapabilityImplementation`
    pronta para `certificar()`."""
    definicao = CapabilityDefinition(
        id=CapabilityId("relatorio-consolidado-de-achados"),
        name="Relatorio consolidado de achados",
        version="1.0.0",
        input_schema=EntradaRelatorioConsolidado.model_json_schema(),
        output_schema=SaidaRelatorioConsolidado.model_json_schema(),
        deterministic=True,
        side_effects=SideEffects.NONE,
        idempotent=True,
    )

    entrada_sucesso = {
        "titulo_missao": "Auditoria de teste",
        "achados": [
            {"codigo": "CLOUD-001", "severidade": "high"},
            {"codigo": "DEP-003", "severidade": "medium"},
            {"codigo": "CLOUD-001", "severidade": "high"},
        ],
    }
    entrada_achado_malformado = {
        "titulo_missao": "Auditoria de teste",
        "achados": ["nao-e-dict"],
    }

    return CapabilityImplementation(
        definition=definicao,
        handler=avaliar_relatorio_consolidado,
        acceptance_tests=[
            AcceptanceTest(
                name="agrega-contagens-por-severidade-e-codigo",
                entrada=entrada_sucesso,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: (
                    saida["total_achados"] == 3
                    and saida["resumo_por_severidade"] == {"high": 2, "medium": 1}
                    and saida["resumo_por_codigo"] == {"CLOUD-001": 2, "DEP-003": 1}
                ),
            ),
            AcceptanceTest(
                name="entrada-sem-titulo_missao-usa-default-mas-tipo-errado-e-rejeitado",
                entrada={"achados": "nao-e-lista"},
                resultado_esperado=ResultadoEsperado.SCHEMA_REJECTION,
            ),
            AcceptanceTest(
                name="achado-nao-dict-e-tratado-como-falha-de-invocacao",
                entrada=entrada_achado_malformado,
                resultado_esperado=ResultadoEsperado.TIMEOUT,
            ),
        ],
    )
