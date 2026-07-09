"""Capability bespoke UI-002 "style={{}} inline estático em componente
React" (Vol.IV Cap.17).

Não generalizada em Skill — `_is_static_style()` é um mini-parser que
separa `style={{...}}` por vírgula (nível de topo, sem contar aninhamento
de parênteses/chaves dentro de chamadas de função ou ternários — mesma
simplificação do legado, replicada fielmente) e avalia cada `key:value`
(shorthand, literal vs variável/função) — não é expressável como um único
regex."""

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

_INLINE_STYLE = re.compile(r"style=\{\{([^}]*)\}\}", re.S)
_LITERAL_KEYWORDS = frozenset({"null", "undefined", "true", "false"})
_NUMERO_COM_UNIDADE = re.compile(r"^-?\d+(\.\d+)?(px|em|rem|%|vh|vw|vmin|vmax|s|ms|ch|ex)?$")


class RegraUi002Spec(BaseModel):
    codigo: str
    agente: str
    severidade: str
    categoria: str
    titulo: str
    causa: str
    remediacao: str


class EntradaUi002(BaseModel):
    tipo: Literal["ui002"] = "ui002"
    caminho: str
    conteudo: str | None = None
    regra: RegraUi002Spec


class AchadoUi002(BaseModel):
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


class SaidaUi002(BaseModel):
    achados: list[AchadoUi002] = Field(default_factory=list)


class EntradaInvalida(Exception):
    """Levantada quando `entrada` não satisfaz `EntradaUi002` — vira
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


def _is_static_style(inner: str) -> bool:
    """Retorna True se `style={{...}}` usa apenas valores literais
    (estáticos). Qualquer variável, função, propriedade de objeto ou
    shorthand → dinâmico → False."""
    stripped = inner.strip()
    if not stripped:
        return False

    for part in stripped.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" not in part:
            return False
        _, _, raw_val = part.partition(":")
        val = raw_val.strip()
        if val.startswith("`"):
            return False
        if val.startswith(("'", '"')):
            continue
        if val in _LITERAL_KEYWORDS:
            continue
        if _NUMERO_COM_UNIDADE.match(val):
            continue
        return False
    return True


def avaliar_ui002(entrada: Any, contexto: ExecutionContext) -> Any:
    del contexto
    try:
        dados = EntradaUi002.model_validate(entrada)
    except Exception as exc:
        raise EntradaInvalida(str(exc)) from exc

    if dados.conteudo is None:
        return SaidaUi002(achados=[]).model_dump()

    text = dados.conteudo
    lines: list[int] = []
    for m in _INLINE_STYLE.finditer(text):
        inner = m.group(1)
        if not _is_static_style(inner):
            continue
        lines.append(_line_of(text, m.start()))

    if not lines:
        return SaidaUi002(achados=[]).model_dump()

    regra = dados.regra
    fingerprint = _computar_fingerprint(regra.agente, regra.categoria, dados.caminho, regra.codigo)
    achado = AchadoUi002(
        codigo=regra.codigo,
        agente=regra.agente,
        severidade=regra.severidade,
        categoria=regra.categoria,
        titulo=regra.titulo,
        descricao=f"{dados.caminho}: style inline estático (linhas {_fmt_lines(lines)}).",
        causa=regra.causa,
        remediacao=regra.remediacao,
        arquivo=dados.caminho,
        fingerprint=fingerprint,
    )
    return SaidaUi002(achados=[achado]).model_dump()


def construir_implementacao() -> CapabilityImplementation:
    definicao = CapabilityDefinition(
        id=CapabilityId("ui002-inline-style-estatico"),
        name="UI-002 style inline estatico",
        version="1.0.0",
        input_schema=EntradaUi002.model_json_schema(),
        output_schema=SaidaUi002.model_json_schema(),
        deterministic=True,
        side_effects=SideEffects.NONE,
        idempotent=True,
    )

    _regra_teste = {
        "codigo": "UI-002",
        "agente": "ui-designer",
        "severidade": "low",
        "categoria": "design-system",
        "titulo": "t",
        "causa": "c",
        "remediacao": "r",
    }
    entrada_sucesso = {
        "caminho": "frontend/src/Card.tsx",
        "conteudo": "<div style={{ color: 'red', padding: 10 }}>x</div>\n",
        "regra": _regra_teste,
    }
    entrada_ok = {
        "caminho": "frontend/src/Card.tsx",
        "conteudo": "<div style={{ color: theme.colors.primary }}>x</div>\n",
        "regra": _regra_teste,
    }

    return CapabilityImplementation(
        definition=definicao,
        handler=avaliar_ui002,
        acceptance_tests=[
            AcceptanceTest(
                name="style-inline-estatico-dispara",
                entrada=entrada_sucesso,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: len(saida["achados"]) == 1,
            ),
            AcceptanceTest(
                name="style-inline-dinamico-nao-dispara",
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
