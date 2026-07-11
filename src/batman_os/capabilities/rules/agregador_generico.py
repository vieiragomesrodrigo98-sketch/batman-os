"""Capability agregadora genérica (Vol.IV Cap.16) — Fase 3 do roadmap de
plataforma, `.claude/plans/peaceful-wondering-hearth.md`, Estágio 3.1.

Composição de Missões multi-step (Playbooks) precisa de UM step cobrindo o
repo INTEIRO para uma regra — mas os handlers migrados
(`regex_sobre_conteudo.py::avaliar_regra_regex`, `toml_dependencias.py::
avaliar_regra_dependencias`) avaliam UM item por invocação (um arquivo, ou
o payload já agregado de dependências). Em vez de reescrever 47+ handlers
para aceitar uma lista, esta fábrica genérica ENVOLVE qualquer handler
existente sem modificá-lo: itera internamente sobre uma lista de itens,
concatenando os achados de cada invocação. Zero mudança nos handlers
originais — eles continuam certificados e usados como estão no scan
por-arquivo de `cli/scan_command.py`.

Falha de UM item nunca derruba o step inteiro (registrada em
`itens_com_erro`) — decisão de escopo deliberada (ver plano, Estágio 3.1):
o tratamento formal de degradação parcial (`PartiallyCompleted`/
`DegradationRecord`, Vol.V Cap.22) fica fora desta fase.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

from batman_os.capabilities.capability_contract import (
    AcceptanceTest,
    CapabilityImplementation,
)
from batman_os.capabilities.operator import ExecutionContext
from batman_os.foundation.types import CapabilityId
from batman_os.runtime.capability_engine import CapabilityDefinition, SideEffects


class EntradaAgregadorGenerico(BaseModel):
    """`capability_alvo` é só documentacional/auditoria (aparece em logs e
    no relatório) — não influencia o despacho, que já está fixado no
    momento em que `construir_implementacao_agregadora()` recebe
    `handler_por_item`."""

    tipo: str = "agregador-generico"
    capability_alvo: str
    itens: list[dict[str, Any]] = Field(default_factory=list)


class SaidaAgregadorGenerico(BaseModel):
    achados: list[dict[str, Any]] = Field(default_factory=list)
    itens_processados: int = 0
    itens_com_erro: list[str] = Field(default_factory=list)


class EntradaInvalida(Exception):
    """Levantada quando `entrada` não satisfaz `EntradaAgregadorGenerico` —
    vira SCHEMA_REJECTION/TIMEOUT no Execution Engine (Vol.III Cap.12), a
    mesma convenção de todo handler já migrado."""


def _avaliar_agregador(
    handler_por_item: Callable[[Any, ExecutionContext], Any],
    entrada: Any,
    contexto: ExecutionContext,
) -> Any:
    try:
        dados = EntradaAgregadorGenerico.model_validate(entrada)
    except Exception as exc:
        raise EntradaInvalida(str(exc)) from exc

    achados: list[dict[str, Any]] = []
    itens_com_erro: list[str] = []
    for indice, item in enumerate(dados.itens):
        try:
            saida_item = handler_por_item(item, contexto)
        except Exception as exc:  # noqa: BLE001 - um item ruim nao derruba o step inteiro
            itens_com_erro.append(f"item[{indice}]: {exc}")
            continue
        achados.extend((saida_item or {}).get("achados", []))

    return SaidaAgregadorGenerico(
        achados=achados,
        itens_processados=len(dados.itens),
        itens_com_erro=itens_com_erro,
    ).model_dump()


def construir_implementacao_agregadora(
    *,
    capability_id: CapabilityId,
    nome: str,
    handler_por_item: Callable[[Any, ExecutionContext], Any],
    acceptance_tests: list[AcceptanceTest],
) -> CapabilityImplementation:
    """Vol.IV Cap.16, secao 16.3 — monta a `CapabilityImplementation`
    pronta para `certificar()`. `handler_por_item` é reaproveitado SEM
    modificação (ex.: `regex_sobre_conteudo.avaliar_regra_regex`)."""
    definicao = CapabilityDefinition(
        id=capability_id,
        name=nome,
        version="1.0.0",
        input_schema=EntradaAgregadorGenerico.model_json_schema(),
        output_schema=SaidaAgregadorGenerico.model_json_schema(),
        deterministic=True,
        side_effects=SideEffects.NONE,
        idempotent=True,
    )

    def _handler(entrada: Any, contexto: ExecutionContext) -> Any:
        return _avaliar_agregador(handler_por_item, entrada, contexto)

    return CapabilityImplementation(
        definition=definicao,
        handler=_handler,
        acceptance_tests=acceptance_tests,
    )


def _acceptance_tests_regex() -> list[AcceptanceTest]:
    regra_teste = {
        "codigo": "TEST-AGG-001",
        "agente": "teste",
        "severidade": "high",
        "categoria": "teste",
        "titulo": "teste",
        "causa": "teste",
        "remediacao": "teste",
        "modo": "presenca",
        "pattern": "SECRET_KEY",
    }
    entrada_sucesso = {
        "capability_alvo": "regex-sobre-conteudo-de-arquivo",
        "itens": [
            {"caminho": "a.py", "conteudo": "SECRET_KEY = 'x'", "regra": regra_teste},
            {"caminho": "b.py", "conteudo": "limpo", "regra": regra_teste},
        ],
    }
    return [
        AcceptanceTest(
            name="agrega-achados-de-multiplos-itens",
            entrada=entrada_sucesso,
            resultado_esperado="success",
            matcher_saida=lambda saida: (
                len(saida["achados"]) == 1 and saida["itens_processados"] == 2
            ),
        ),
        AcceptanceTest(
            name="capability_alvo-ausente-e-rejeitada",
            entrada={"itens": []},
            resultado_esperado="schema-rejection",
        ),
        AcceptanceTest(
            name="itens-com-tipo-errado-e-tratado-como-falha",
            entrada={"capability_alvo": "x", "itens": "nao-e-lista"},
            resultado_esperado="timeout",
        ),
    ]


def construir_implementacao_agregador_regex() -> CapabilityImplementation:
    from batman_os.capabilities.rules.regex_sobre_conteudo import avaliar_regra_regex

    return construir_implementacao_agregadora(
        capability_id=CapabilityId("regex-sobre-conteudo-de-arquivo-agregador"),
        nome="Regex sobre conteudo de arquivo (agregador multi-arquivo)",
        handler_por_item=avaliar_regra_regex,
        acceptance_tests=_acceptance_tests_regex(),
    )


def _acceptance_tests_dependencias() -> list[AcceptanceTest]:
    import json as _json

    regra_teste = {
        "codigo": "TEST-AGG-DEP-001",
        "agente": "teste",
        "severidade": "high",
        "categoria": "teste",
        "titulo": "teste",
        "causa": "teste",
        "remediacao": "teste",
        "aspecto": "sem_limite_superior",
    }
    entrada_sucesso = {
        "capability_alvo": "toml-dependencias",
        "itens": [
            {
                "caminho": "pyproject.toml",
                "conteudo": _json.dumps(
                    {"pyproject_texto": '[project]\ndependencies = ["fastapi>=0.1"]\n'}
                ),
                "regra": regra_teste,
            }
        ],
    }
    return [
        AcceptanceTest(
            name="agrega-achado-de-dependencia-sem-teto",
            entrada=entrada_sucesso,
            resultado_esperado="success",
            matcher_saida=lambda saida: (
                len(saida["achados"]) == 1 and saida["itens_processados"] == 1
            ),
        ),
        AcceptanceTest(
            name="capability_alvo-ausente-e-rejeitada",
            entrada={"itens": []},
            resultado_esperado="schema-rejection",
        ),
        AcceptanceTest(
            name="itens-com-tipo-errado-e-tratado-como-falha",
            entrada={"capability_alvo": "x", "itens": "nao-e-lista"},
            resultado_esperado="timeout",
        ),
    ]


def construir_implementacao_agregador_dependencias() -> CapabilityImplementation:
    from batman_os.capabilities.rules.toml_dependencias import avaliar_regra_dependencias

    return construir_implementacao_agregadora(
        capability_id=CapabilityId("toml-dependencias-agregador"),
        nome="Dependencias TOML (agregador multi-arquivo)",
        handler_por_item=avaliar_regra_dependencias,
        acceptance_tests=_acceptance_tests_dependencias(),
    )
