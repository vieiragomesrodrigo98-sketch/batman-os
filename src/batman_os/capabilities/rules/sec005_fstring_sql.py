"""Capability bespoke SEC-005 "SQL com f-string" (Vol.IV Cap.17).

Não generalizada numa Skill — checagem sobre `ast.Call` que combina nome
de método (`.execute(`) com o TIPO do primeiro argumento posicional
(`ast.JoinedStr`, o nó AST de f-string) — diferente de `ast_kwarg_ausente`
(que checa AUSÊNCIA de kwarg, não o tipo de um argumento posicional) e de
`ast_padrao_ausente` (que checa corpo/contexto via regex, não o tipo do
nó do próprio Call). Mesma equivalência de fingerprint de sempre: o
legado agrega todas as linhas num único achado por arquivo (`fmt_lines`),
que já é o formato usado aqui."""

from __future__ import annotations

import ast
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


class RegraSec005Spec(BaseModel):
    codigo: str
    agente: str
    severidade: str
    categoria: str
    titulo: str
    causa: str
    remediacao: str


class EntradaSec005(BaseModel):
    tipo: Literal["sec005"] = "sec005"
    caminho: str
    conteudo: str | None = None
    regra: RegraSec005Spec


class AchadoSec005(BaseModel):
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


class SaidaSec005(BaseModel):
    achados: list[AchadoSec005] = Field(default_factory=list)


class EntradaInvalida(Exception):
    """Levantada quando `entrada` não satisfaz `EntradaSec005` — vira
    SCHEMA_REJECTION no Execution Engine (Vol.III Cap.12)."""


def _computar_fingerprint(agente: str, categoria: str, caminho: str, codigo: str) -> str:
    import hashlib

    normalizado = caminho.replace("\\", "/")
    bruto = f"{agente}|{categoria}|{normalizado}|{codigo}|"
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()


def _execute_com_fstring(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "execute"
        and bool(node.args)
        and isinstance(node.args[0], ast.JoinedStr)
    )


def avaliar_sec005(entrada: Any, contexto: ExecutionContext) -> Any:
    del contexto
    try:
        dados = EntradaSec005.model_validate(entrada)
    except Exception as exc:
        raise EntradaInvalida(str(exc)) from exc

    texto = dados.conteudo or ""
    try:
        tree = ast.parse(texto)
    except SyntaxError:
        return SaidaSec005(achados=[]).model_dump()

    dispara = any(_execute_com_fstring(node) for node in ast.walk(tree))
    if not dispara:
        return SaidaSec005(achados=[]).model_dump()

    regra = dados.regra
    fingerprint = _computar_fingerprint(regra.agente, regra.categoria, dados.caminho, regra.codigo)
    achado = AchadoSec005(
        codigo=regra.codigo,
        agente=regra.agente,
        severidade=regra.severidade,
        categoria=regra.categoria,
        titulo=regra.titulo,
        descricao=f"{dados.caminho}: .execute() recebe f-string.",
        causa=regra.causa,
        remediacao=regra.remediacao,
        arquivo=dados.caminho,
        fingerprint=fingerprint,
    )
    return SaidaSec005(achados=[achado]).model_dump()


def construir_implementacao() -> CapabilityImplementation:
    definicao = CapabilityDefinition(
        id=CapabilityId("sec005-fstring-sql"),
        name="SEC-005 SQL com f-string",
        version="1.0.0",
        input_schema=EntradaSec005.model_json_schema(),
        output_schema=SaidaSec005.model_json_schema(),
        deterministic=True,
        side_effects=SideEffects.NONE,
        idempotent=True,
    )

    _regra_teste = {
        "codigo": "SEC-005",
        "agente": "security-engineer",
        "severidade": "medium",
        "categoria": "sql",
        "titulo": "t",
        "causa": "c",
        "remediacao": "r",
    }
    entrada_sucesso = {
        "caminho": "api/x.py",
        "conteudo": 'cursor.execute(f"SELECT * FROM t WHERE id={id}")\n',
        "regra": _regra_teste,
    }
    entrada_ok = {
        "caminho": "api/y.py",
        "conteudo": "cursor.execute('SELECT * FROM t WHERE id=%s', (id,))\n",
        "regra": _regra_teste,
    }

    return CapabilityImplementation(
        definition=definicao,
        handler=avaliar_sec005,
        acceptance_tests=[
            AcceptanceTest(
                name="execute-com-fstring-dispara-um-achado",
                entrada=entrada_sucesso,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: len(saida["achados"]) == 1,
            ),
            AcceptanceTest(
                name="execute-parametrizado-nao-dispara",
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
                entrada={"caminho": "a.py", "conteudo": "x", "regra": {"severidade": 123}},
                resultado_esperado=ResultadoEsperado.TIMEOUT,
            ),
        ],
    )
