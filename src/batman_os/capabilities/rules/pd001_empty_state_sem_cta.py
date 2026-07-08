"""Capability bespoke PD-001 "empty state sem CTA" (Vol.IV Cap.17).

Não generalizada em `janela_contexto_regex` — a janela é por CARACTERE
(`text[m.start()-300:m.end()+300]`), não por LINHA como a Skill assume, e
só a PRIMEIRA ocorrência do padrão de "empty state" no arquivo importa
(`.search()`, não `.finditer()`) — múltiplas ocorrências no mesmo arquivo
não geram achados adicionais."""

from __future__ import annotations

import re
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

_EMPTY_MSG = re.compile(
    r"Nenhum[a]?\s+\w+|sem sinais|sem posições|nothing here|Não há|não encontrado|Nada por aqui",
    re.I,
)
_HAS_CTA = re.compile(r"<Link\b|<NavLink\b|<button\b|href=|to=|ChevronRight|→|CTA", re.I)


class RegraPd001Spec(BaseModel):
    codigo: str
    agente: str
    severidade: str
    categoria: str
    titulo: str
    causa: str
    remediacao: str


class EntradaPd001(BaseModel):
    tipo: Literal["pd001"] = "pd001"
    caminho: str
    conteudo: str | None = None
    regra: RegraPd001Spec


class AchadoPd001(BaseModel):
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


class SaidaPd001(BaseModel):
    achados: list[AchadoPd001] = Field(default_factory=list)


class EntradaInvalida(Exception):
    """Levantada quando `entrada` não satisfaz `EntradaPd001` — vira
    SCHEMA_REJECTION no Execution Engine (Vol.III Cap.12)."""


def _computar_fingerprint(agente: str, categoria: str, caminho: str, codigo: str) -> str:
    import hashlib

    normalizado = caminho.replace("\\", "/")
    bruto = f"{agente}|{categoria}|{normalizado}|{codigo}|"
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()


def avaliar_pd001(entrada: Any, contexto: ExecutionContext) -> Any:
    del contexto
    try:
        dados = EntradaPd001.model_validate(entrada)
    except Exception as exc:
        raise EntradaInvalida(str(exc)) from exc

    if dados.conteudo is None:
        return SaidaPd001(achados=[]).model_dump()

    text = dados.conteudo
    m = _EMPTY_MSG.search(text)
    if not m:
        return SaidaPd001(achados=[]).model_dump()

    window = text[max(0, m.start() - 300) : m.end() + 300]
    if _HAS_CTA.search(window):
        return SaidaPd001(achados=[]).model_dump()

    ln = text.count("\n", 0, m.start()) + 1
    regra = dados.regra
    fingerprint = _computar_fingerprint(regra.agente, regra.categoria, dados.caminho, regra.codigo)
    achado = AchadoPd001(
        codigo=regra.codigo,
        agente=regra.agente,
        severidade=regra.severidade,
        categoria=regra.categoria,
        titulo=regra.titulo,
        descricao=f"{dados.caminho}:{ln}: empty state sem CTA — '{m.group(0)[:50]}'.",
        causa=regra.causa,
        remediacao=regra.remediacao,
        arquivo=dados.caminho,
        fingerprint=fingerprint,
    )
    return SaidaPd001(achados=[achado]).model_dump()


def construir_implementacao() -> CapabilityImplementation:
    definicao = CapabilityDefinition(
        id=CapabilityId("pd001-empty-state-sem-cta"),
        name="PD-001 empty state sem CTA",
        version="1.0.0",
        input_schema=EntradaPd001.model_json_schema(),
        output_schema=SaidaPd001.model_json_schema(),
        deterministic=True,
        side_effects=SideEffects.NONE,
        idempotent=True,
    )

    _regra_teste = {
        "codigo": "PD-001",
        "agente": "product-designer",
        "severidade": "medium",
        "categoria": "completude",
        "titulo": "t",
        "causa": "c",
        "remediacao": "r",
    }
    entrada_sucesso = {
        "caminho": "frontend/src/Signals.tsx",
        "conteudo": "<div>Nenhum sinal encontrado</div>\n",
        "regra": _regra_teste,
    }
    entrada_ok = {
        "caminho": "frontend/src/Signals.tsx",
        "conteudo": '<div>Nenhum sinal encontrado</div>\n<Link to="/explorar">Explorar →</Link>\n',
        "regra": _regra_teste,
    }

    return CapabilityImplementation(
        definition=definicao,
        handler=avaliar_pd001,
        acceptance_tests=[
            AcceptanceTest(
                name="empty-state-sem-cta-dispara",
                entrada=entrada_sucesso,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: len(saida["achados"]) == 1,
            ),
            AcceptanceTest(
                name="empty-state-com-cta-nao-dispara",
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
                    "caminho": "frontend/src/x.tsx",
                    "conteudo": "x",
                    "regra": {"severidade": 123},
                },
                resultado_esperado=ResultadoEsperado.TIMEOUT,
            ),
        ],
    )
