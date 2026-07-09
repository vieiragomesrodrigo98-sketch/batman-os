"""Capability bespoke A11Y-002 "onClick em elemento não-interativo
(div/span) sem suporte a teclado" (Vol.IV Cap.17).

Não generalizada em Skill — usa `_jsx_opening_tags()`, um mini-scanner
que rastreia profundidade de `{}` para achar o fim REAL da tag JSX
(`<div className={x > 0 ? 'a' : 'b'}>` tem um `>` dentro de `{}` que um
regex simples de "até o primeiro `>`" confundiria com o fechamento da
tag) — precisa de um parser de estado, não de um único padrão regex."""

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

_ABERTURA_DIV_SPAN = re.compile(r"<(div|span)\b", re.I)


class RegraA11y002Spec(BaseModel):
    codigo: str
    agente: str
    severidade: str
    categoria: str
    titulo: str
    causa: str
    remediacao: str


class EntradaA11y002(BaseModel):
    tipo: Literal["a11y002"] = "a11y002"
    caminho: str
    conteudo: str | None = None
    regra: RegraA11y002Spec


class AchadoA11y002(BaseModel):
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


class SaidaA11y002(BaseModel):
    achados: list[AchadoA11y002] = Field(default_factory=list)


class EntradaInvalida(Exception):
    """Levantada quando `entrada` não satisfaz `EntradaA11y002` — vira
    SCHEMA_REJECTION no Execution Engine (Vol.III Cap.12)."""


def _computar_fingerprint(agente: str, categoria: str, caminho: str, codigo: str) -> str:
    import hashlib

    normalizado = caminho.replace("\\", "/")
    bruto = f"{agente}|{categoria}|{normalizado}|{codigo}|"
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()


def _fmt_lines(lines: list[int]) -> str:
    return ",".join(str(x) for x in sorted(set(lines)))


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _jsx_opening_tags(text: str) -> list[tuple[int, str]]:
    """Yield (start, tag_text) para tags de abertura <div>/<span>,
    rastreando profundidade de `{}`."""
    resultado: list[tuple[int, str]] = []
    i = 0
    while i < len(text):
        m = _ABERTURA_DIV_SPAN.search(text[i:])
        if not m:
            break
        start = i + m.start()
        j = start + len(m.group(0))
        depth = 0
        while j < len(text):
            c = text[j]
            if c == "{":
                depth += 1
            elif c == "}":
                if depth > 0:
                    depth -= 1
            elif depth == 0:
                if c == "/" and j + 1 < len(text) and text[j + 1] == ">":
                    j += 2
                    break
                elif c == ">":
                    j += 1
                    break
            j += 1
        resultado.append((start, text[start:j]))
        i = start + 1
    return resultado


def avaliar_a11y002(entrada: Any, contexto: ExecutionContext) -> Any:
    del contexto
    try:
        dados = EntradaA11y002.model_validate(entrada)
    except Exception as exc:
        raise EntradaInvalida(str(exc)) from exc

    if dados.conteudo is None:
        return SaidaA11y002(achados=[]).model_dump()

    text = dados.conteudo
    bad = [
        _line_of(text, start)
        for start, tag in _jsx_opening_tags(text)
        if "onClick" in tag and not ("role=" in tag and "onKeyDown" in tag)
    ]

    if not bad:
        return SaidaA11y002(achados=[]).model_dump()

    regra = dados.regra
    fingerprint = _computar_fingerprint(regra.agente, regra.categoria, dados.caminho, regra.codigo)
    achado = AchadoA11y002(
        codigo=regra.codigo,
        agente=regra.agente,
        severidade=regra.severidade,
        categoria=regra.categoria,
        titulo=regra.titulo,
        descricao=f"{dados.caminho}: onClick em div/span sem teclado (linhas {_fmt_lines(bad)}).",
        causa=regra.causa,
        remediacao=regra.remediacao,
        arquivo=dados.caminho,
        fingerprint=fingerprint,
    )
    return SaidaA11y002(achados=[achado]).model_dump()


def construir_implementacao() -> CapabilityImplementation:
    definicao = CapabilityDefinition(
        id=CapabilityId("a11y002-onclick-sem-teclado"),
        name="A11Y-002 onClick sem suporte a teclado",
        version="1.0.0",
        input_schema=EntradaA11y002.model_json_schema(),
        output_schema=SaidaA11y002.model_json_schema(),
        deterministic=True,
        side_effects=SideEffects.NONE,
        idempotent=True,
    )

    _regra_teste = {
        "codigo": "A11Y-002",
        "agente": "ux-designer",
        "severidade": "low",
        "categoria": "acessibilidade",
        "titulo": "t",
        "causa": "c",
        "remediacao": "r",
    }
    entrada_sucesso = {
        "caminho": "frontend/src/Card.tsx",
        "conteudo": "<div onClick={handleClick}>texto</div>\n",
        "regra": _regra_teste,
    }
    entrada_ok = {
        "caminho": "frontend/src/Card.tsx",
        "conteudo": (
            '<div onClick={handleClick} role="button" onKeyDown={handleKey}>texto</div>\n'
        ),
        "regra": _regra_teste,
    }

    return CapabilityImplementation(
        definition=definicao,
        handler=avaliar_a11y002,
        acceptance_tests=[
            AcceptanceTest(
                name="onclick-sem-teclado-dispara",
                entrada=entrada_sucesso,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: len(saida["achados"]) == 1,
            ),
            AcceptanceTest(
                name="onclick-com-role-e-onkeydown-nao-dispara",
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
