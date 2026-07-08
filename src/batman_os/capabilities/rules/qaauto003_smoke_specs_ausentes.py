"""Capability bespoke QA-AUTO-003 "spec Playwright P0 ausente na suíte de
smoke E2E" (Vol.IV Cap.17).

Não generalizada em Skill — checagem de existência de uma LISTA FIXA de
paths (não um padrão de conteúdo): se QUALQUER um estiver ausente, 1
achado lista TODOS os ausentes, com `caminho` = PRIMEIRO ausente (replica
`arquivos[0]["path"]` do legado, que é `missing[0]`)."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field

from batman_os.capabilities.capability_contract import (
    AcceptanceTest,
    CapabilityImplementation,
    ResultadoEsperado,
)
from batman_os.capabilities.operator import ExecutionContext
from batman_os.foundation.types import CapabilityId
from batman_os.runtime.capability_engine import CapabilityDefinition, SideEffects


class RegraQaAuto003Spec(BaseModel):
    codigo: str
    agente: str
    severidade: str
    categoria: str
    titulo: str
    causa: str
    remediacao: str


class EntradaQaAuto003(BaseModel):
    tipo: Literal["qaauto003"] = "qaauto003"
    caminho: str
    conteudo: str | None = None
    regra: RegraQaAuto003Spec


class AchadoQaAuto003(BaseModel):
    codigo: str
    agente: str
    severidade: str
    categoria: str
    titulo: str
    descricao: str
    causa: str
    remediacao: str
    arquivo: str
    chave: str = ""
    fingerprint: str = ""


class SaidaQaAuto003(BaseModel):
    achados: list[AchadoQaAuto003] = Field(default_factory=list)


class EntradaInvalida(Exception):
    """Levantada quando `entrada` não satisfaz `EntradaQaAuto003` — vira
    SCHEMA_REJECTION no Execution Engine (Vol.III Cap.12)."""


def _computar_fingerprint(agente: str, categoria: str, caminho: str, codigo: str) -> str:
    import hashlib

    normalizado = caminho.replace("\\", "/")
    bruto = f"{agente}|{categoria}|{normalizado}|{codigo}|"
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()


def avaliar_qaauto003(entrada: Any, contexto: ExecutionContext) -> Any:
    del contexto
    try:
        dados = EntradaQaAuto003.model_validate(entrada)
    except Exception as exc:
        raise EntradaInvalida(str(exc)) from exc

    if dados.conteudo is None:
        return SaidaQaAuto003(achados=[]).model_dump()

    payload = json.loads(dados.conteudo)
    missing: list[str] = payload.get("missing", [])
    total: int = payload.get("total", 0)

    if not missing:
        return SaidaQaAuto003(achados=[]).model_dump()

    regra = dados.regra
    caminho = missing[0]
    fingerprint = _computar_fingerprint(regra.agente, regra.categoria, caminho, regra.codigo)
    achado = AchadoQaAuto003(
        codigo=regra.codigo,
        agente=regra.agente,
        severidade=regra.severidade,
        categoria=regra.categoria,
        titulo=regra.titulo,
        descricao=f"{len(missing)}/{total} spec(s) P0 ausentes: {', '.join(missing)}.",
        causa=regra.causa,
        remediacao=regra.remediacao,
        arquivo=caminho,
        fingerprint=fingerprint,
    )
    return SaidaQaAuto003(achados=[achado]).model_dump()


def construir_implementacao() -> CapabilityImplementation:
    definicao = CapabilityDefinition(
        id=CapabilityId("qaauto003-smoke-specs-ausentes"),
        name="QA-AUTO-003 spec Playwright P0 ausente",
        version="1.0.0",
        input_schema=EntradaQaAuto003.model_json_schema(),
        output_schema=SaidaQaAuto003.model_json_schema(),
        deterministic=True,
        side_effects=SideEffects.NONE,
        idempotent=True,
    )

    _regra_teste = {
        "codigo": "QA-AUTO-003",
        "agente": "qa-automation",
        "severidade": "medium",
        "categoria": "cobertura",
        "titulo": "t",
        "causa": "c",
        "remediacao": "r",
    }
    entrada_sucesso = {
        "caminho": "e2e/smoke",
        "conteudo": json.dumps({"missing": ["e2e/smoke/landing.spec.ts"], "total": 7}),
        "regra": _regra_teste,
    }
    entrada_ok = {
        "caminho": "e2e/smoke",
        "conteudo": json.dumps({"missing": [], "total": 7}),
        "regra": _regra_teste,
    }

    return CapabilityImplementation(
        definition=definicao,
        handler=avaliar_qaauto003,
        acceptance_tests=[
            AcceptanceTest(
                name="spec-p0-ausente-dispara",
                entrada=entrada_sucesso,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: len(saida["achados"]) == 1,
            ),
            AcceptanceTest(
                name="todos-os-specs-presentes-nao-dispara",
                entrada=entrada_ok,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: saida["achados"] == [],
            ),
            AcceptanceTest(
                name="entrada-sem-campo-obrigatorio-e-rejeitada",
                entrada={"conteudo": "x"},  # falta 'caminho'
                resultado_esperado=ResultadoEsperado.SCHEMA_REJECTION,
            ),
            AcceptanceTest(
                name="regra-com-tipo-de-campo-invalido-e-tratada-como-falha-de-invocacao",
                entrada={
                    "caminho": "e2e/smoke",
                    "conteudo": "x",
                    "regra": {"severidade": 123},
                },
                resultado_esperado=ResultadoEsperado.TIMEOUT,
            ),
        ],
    )
