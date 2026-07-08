"""Capability bespoke SUP-001 "exceção silenciada" (Vol.IV Cap.17).

Não generalizada numa Skill — combinação única de checagens sobre
`ast.ExceptHandler` que não se repete em nenhum outro código catalogado:
(1) tipo de exceção contra uma safelist (`ImportError`/`ModuleNotFoundError`/
`HTTPException` são aceitáveis sem log — dependência opcional, auth
opcional); (2) corpo é só `pass`/`...`; (3) corpo tem log/print/raise;
(4) corpo GUARDA a exceção numa variável para re-raise posterior (regex
com o NOME da variável do `except ... as nome` interpolado dinamicamente —
não é um padrão fixo, é construído por ocorrência). Dispara quando
`(not has_log or has_pass) and not exc_stored`.

Mesma equivalência de fingerprint já estabelecida (BE-006/MOB-003/EH-009):
o legado `yield`a por ExceptHandler, mas sem `chave` todas as ocorrências
do mesmo arquivo colapsam no mesmo fingerprint — 1 achado agregado por
arquivo é equivalente."""

from __future__ import annotations

import ast
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

_SAFE_EXCEPTIONS = frozenset({"ImportError", "ModuleNotFoundError", "HTTPException"})


class RegraSup001Spec(BaseModel):
    codigo: str
    agente: str
    severidade: str
    categoria: str
    titulo: str
    causa: str
    remediacao: str


class EntradaSup001(BaseModel):
    tipo: Literal["sup001"] = "sup001"
    caminho: str
    conteudo: str | None = None
    regra: RegraSup001Spec


class AchadoSup001(BaseModel):
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


class SaidaSup001(BaseModel):
    achados: list[AchadoSup001] = Field(default_factory=list)


class EntradaInvalida(Exception):
    """Levantada quando `entrada` não satisfaz `EntradaSup001` — vira
    SCHEMA_REJECTION no Execution Engine (Vol.III Cap.12)."""


def _computar_fingerprint(agente: str, categoria: str, caminho: str, codigo: str) -> str:
    import hashlib

    normalizado = caminho.replace("\\", "/")
    bruto = f"{agente}|{categoria}|{normalizado}|{codigo}|"
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()


def _except_silenciado(node: ast.ExceptHandler, texto: str) -> bool:
    if node.type is not None:
        exc_name = (
            node.type.id if isinstance(node.type, ast.Name) else getattr(node.type, "id", None)
        )
        if exc_name in _SAFE_EXCEPTIONS:
            return False

    body_src = "\n".join(ast.get_source_segment(texto, stmt) or "" for stmt in node.body)
    has_pass = all(
        isinstance(stmt, ast.Pass)
        or (
            isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Constant)
            and stmt.value.value is ...
        )
        for stmt in node.body
    )
    has_log = bool(re.search(r"log|logger|print|raise", body_src, re.IGNORECASE))
    exc_stored = node.name is not None and bool(
        re.search(rf"\b\w+\s*=\s*{re.escape(node.name)}\b", body_src)
    )
    return (not has_log or has_pass) and not exc_stored


def avaliar_sup001(entrada: Any, contexto: ExecutionContext) -> Any:
    del contexto
    try:
        dados = EntradaSup001.model_validate(entrada)
    except Exception as exc:
        raise EntradaInvalida(str(exc)) from exc

    texto = dados.conteudo or ""
    try:
        tree = ast.parse(texto)
    except SyntaxError:
        return SaidaSup001(achados=[]).model_dump()

    dispara = any(
        _except_silenciado(node, texto)
        for node in ast.walk(tree)
        if isinstance(node, ast.ExceptHandler)
    )
    if not dispara:
        return SaidaSup001(achados=[]).model_dump()

    regra = dados.regra
    fingerprint = _computar_fingerprint(regra.agente, regra.categoria, dados.caminho, regra.codigo)
    achado = AchadoSup001(
        codigo=regra.codigo,
        agente=regra.agente,
        severidade=regra.severidade,
        categoria=regra.categoria,
        titulo=regra.titulo,
        descricao=f"{dados.caminho}: except silenciado.",
        causa=regra.causa,
        remediacao=regra.remediacao,
        arquivo=dados.caminho,
        fingerprint=fingerprint,
    )
    return SaidaSup001(achados=[achado]).model_dump()


def construir_implementacao() -> CapabilityImplementation:
    definicao = CapabilityDefinition(
        id=CapabilityId("sup001-excecao-silenciada"),
        name="SUP-001 excecao silenciada",
        version="1.0.0",
        input_schema=EntradaSup001.model_json_schema(),
        output_schema=SaidaSup001.model_json_schema(),
        deterministic=True,
        side_effects=SideEffects.NONE,
        idempotent=True,
    )

    _regra_teste = {
        "codigo": "SUP-001",
        "agente": "support",
        "severidade": "medium",
        "categoria": "tratamento-de-erros",
        "titulo": "t",
        "causa": "c",
        "remediacao": "r",
    }
    entrada_sucesso = {
        "caminho": "api/x.py",
        "conteudo": "try:\n    fazer_algo()\nexcept Exception:\n    pass\n",
        "regra": _regra_teste,
    }
    entrada_ok = {
        "caminho": "api/y.py",
        "conteudo": ("try:\n    fazer_algo()\nexcept Exception:\n    logger.exception('falhou')\n"),
        "regra": _regra_teste,
    }

    return CapabilityImplementation(
        definition=definicao,
        handler=avaliar_sup001,
        acceptance_tests=[
            AcceptanceTest(
                name="except-pass-sem-log-dispara-um-achado",
                entrada=entrada_sucesso,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: len(saida["achados"]) == 1,
            ),
            AcceptanceTest(
                name="except-com-log-nao-dispara",
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
