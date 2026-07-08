"""Capability bespoke A11Y-003 "<input> sem label associado" (Vol.IV
Cap.17).

Não generalizada em `janela_contexto_regex` — três mecanismos de exclusão
DIFERENTES no mesmo achado (nenhuma combinação de campos da Skill cobre
isso): (1) aria-label na PRÓPRIA tag OU numa janela de 5 linhas PRA
FRENTE; (2) gate de ARQUIVO INTEIRO — `<label htmlFor=`/`<label for=`
em QUALQUER lugar do arquivo suprime TODOS os inputs dele; (3) janela de
6 linhas PRA TRÁS procurando `<label` (wrapper implícito). Além disso, o
regex de `<input>` usa `re.S` (DOTALL) — a tag JSX pode se espalhar por
múltiplas linhas (`janela_contexto_regex` opera por LINHA, não suporta
padrão multi-linha na âncora). 1 achado POR ARQUIVO (não por ocorrência),
agregando todas as linhas ofensoras via `fmt_lines`."""

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

_INPUT = re.compile(r"<input\b[^>]*?>", re.S | re.I)
_LABEL_FOR = re.compile(r"<label\b[^>]*?(?:htmlFor|for)=", re.I)
_LABEL_ANY = re.compile(r"<label\b", re.I)
_ARIA_LABEL = re.compile(r"aria-label=|aria-labelledby=", re.I)


class RegraA11y003Spec(BaseModel):
    codigo: str
    agente: str
    severidade: str
    categoria: str
    titulo: str
    causa: str
    remediacao: str


class EntradaA11y003(BaseModel):
    tipo: Literal["a11y003"] = "a11y003"
    caminho: str
    conteudo: str | None = None
    regra: RegraA11y003Spec


class AchadoA11y003(BaseModel):
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


class SaidaA11y003(BaseModel):
    achados: list[AchadoA11y003] = Field(default_factory=list)


class EntradaInvalida(Exception):
    """Levantada quando `entrada` não satisfaz `EntradaA11y003` — vira
    SCHEMA_REJECTION no Execution Engine (Vol.III Cap.12)."""


def _computar_fingerprint(agente: str, categoria: str, caminho: str, codigo: str) -> str:
    import hashlib

    normalizado = caminho.replace("\\", "/")
    bruto = f"{agente}|{categoria}|{normalizado}|{codigo}|"
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _fmt_lines(lines: list[int]) -> str:
    return ",".join(str(x) for x in sorted(set(lines)))


def avaliar_a11y003(entrada: Any, contexto: ExecutionContext) -> Any:
    del contexto
    try:
        dados = EntradaA11y003.model_validate(entrada)
    except Exception as exc:
        raise EntradaInvalida(str(exc)) from exc

    if dados.conteudo is None:
        return SaidaA11y003(achados=[]).model_dump()

    text = dados.conteudo
    split = text.splitlines()
    linhas: list[int] = []

    for m in _INPUT.finditer(text):
        tag = m.group(0)
        if 'type="hidden"' in tag or "type='hidden'" in tag:
            continue
        ln = _line_of(text, m.start())
        vicinity = "\n".join(split[ln - 1 : min(ln + 5, len(split))])
        if _ARIA_LABEL.search(tag) or _ARIA_LABEL.search(vicinity):
            continue
        if _LABEL_FOR.search(text):
            continue
        window = "\n".join(split[max(0, ln - 7) : ln - 1])
        if _LABEL_ANY.search(window):
            continue
        linhas.append(ln)

    if not linhas:
        return SaidaA11y003(achados=[]).model_dump()

    regra = dados.regra
    fingerprint = _computar_fingerprint(regra.agente, regra.categoria, dados.caminho, regra.codigo)
    achado = AchadoA11y003(
        codigo=regra.codigo,
        agente=regra.agente,
        severidade=regra.severidade,
        categoria=regra.categoria,
        titulo=regra.titulo,
        descricao=f"{dados.caminho}: <input> sem label (linhas {_fmt_lines(linhas)}).",
        causa=regra.causa,
        remediacao=regra.remediacao,
        arquivo=dados.caminho,
        fingerprint=fingerprint,
    )
    return SaidaA11y003(achados=[achado]).model_dump()


def construir_implementacao() -> CapabilityImplementation:
    definicao = CapabilityDefinition(
        id=CapabilityId("a11y003-input-sem-label"),
        name="A11Y-003 input sem label associado",
        version="1.0.0",
        input_schema=EntradaA11y003.model_json_schema(),
        output_schema=SaidaA11y003.model_json_schema(),
        deterministic=True,
        side_effects=SideEffects.NONE,
        idempotent=True,
    )

    _regra_teste = {
        "codigo": "A11Y-003",
        "agente": "accessibility-specialist",
        "severidade": "medium",
        "categoria": "acessibilidade",
        "titulo": "t",
        "causa": "c",
        "remediacao": "r",
    }
    entrada_sucesso = {
        "caminho": "frontend/src/Form.tsx",
        "conteudo": '<div>\n<input type="text" />\n</div>\n',
        "regra": _regra_teste,
    }
    entrada_ok = {
        "caminho": "frontend/src/Form.tsx",
        "conteudo": '<div>\n<input type="text" aria-label="Nome" />\n</div>\n',
        "regra": _regra_teste,
    }

    return CapabilityImplementation(
        definition=definicao,
        handler=avaliar_a11y003,
        acceptance_tests=[
            AcceptanceTest(
                name="input-sem-label-dispara",
                entrada=entrada_sucesso,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: len(saida["achados"]) == 1,
            ),
            AcceptanceTest(
                name="input-com-aria-label-nao-dispara",
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
