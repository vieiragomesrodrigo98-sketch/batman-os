"""Capability bespoke SEC-007 "DDL no import do módulo" (Vol.IV Cap.17).

Não generalizada numa Skill — itera SOMENTE `tree.body` (nível de módulo,
não `ast.walk` recursivo, que pegaria DDL dentro de funções também — aqui
o risco é ESPECIFICAMENTE código que roda no MOMENTO DO IMPORT), filtra
`ast.Expr` envolvendo `ast.Call`, aplica regex no `source_segment` desse
nó. Diferente de SEC-005 (percorre TODO o AST) e de `ast_padrao_ausente`
(seleciona por ClassDef/FunctionDef/Call, não por posição no nível do
módulo)."""

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

_DDL_RE = re.compile(r"(ALTER|CREATE)\s+TABLE", re.IGNORECASE)
_MIGRATE_RE = re.compile(r"_?run_migrations|\bmigrate\s*\(")


class RegraSec007Spec(BaseModel):
    codigo: str
    agente: str
    severidade: str
    categoria: str
    titulo: str
    causa: str
    remediacao: str


class EntradaSec007(BaseModel):
    tipo: Literal["sec007"] = "sec007"
    caminho: str
    conteudo: str | None = None
    regra: RegraSec007Spec


class AchadoSec007(BaseModel):
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


class SaidaSec007(BaseModel):
    achados: list[AchadoSec007] = Field(default_factory=list)


class EntradaInvalida(Exception):
    """Levantada quando `entrada` não satisfaz `EntradaSec007` — vira
    SCHEMA_REJECTION no Execution Engine (Vol.III Cap.12)."""


def _computar_fingerprint(agente: str, categoria: str, caminho: str, codigo: str) -> str:
    import hashlib

    normalizado = caminho.replace("\\", "/")
    bruto = f"{agente}|{categoria}|{normalizado}|{codigo}|"
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()


def _ddl_no_nivel_modulo(texto: str, tree: ast.Module) -> bool:
    for node in tree.body:
        if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)):
            continue
        seg = ast.get_source_segment(texto, node) or ""
        if _DDL_RE.search(seg) or _MIGRATE_RE.search(seg):
            return True
    return False


def avaliar_sec007(entrada: Any, contexto: ExecutionContext) -> Any:
    del contexto
    try:
        dados = EntradaSec007.model_validate(entrada)
    except Exception as exc:
        raise EntradaInvalida(str(exc)) from exc

    texto = dados.conteudo or ""
    try:
        tree = ast.parse(texto)
    except SyntaxError:
        return SaidaSec007(achados=[]).model_dump()

    if not _ddl_no_nivel_modulo(texto, tree):
        return SaidaSec007(achados=[]).model_dump()

    regra = dados.regra
    fingerprint = _computar_fingerprint(regra.agente, regra.categoria, dados.caminho, regra.codigo)
    achado = AchadoSec007(
        codigo=regra.codigo,
        agente=regra.agente,
        severidade=regra.severidade,
        categoria=regra.categoria,
        titulo=regra.titulo,
        descricao=f"{dados.caminho}: migração/DDL em nível de módulo.",
        causa=regra.causa,
        remediacao=regra.remediacao,
        arquivo=dados.caminho,
        fingerprint=fingerprint,
    )
    return SaidaSec007(achados=[achado]).model_dump()


def construir_implementacao() -> CapabilityImplementation:
    definicao = CapabilityDefinition(
        id=CapabilityId("sec007-ddl-no-import"),
        name="SEC-007 DDL no import do modulo",
        version="1.0.0",
        input_schema=EntradaSec007.model_json_schema(),
        output_schema=SaidaSec007.model_json_schema(),
        deterministic=True,
        side_effects=SideEffects.NONE,
        idempotent=True,
    )

    _regra_teste = {
        "codigo": "SEC-007",
        "agente": "security-engineer",
        "severidade": "medium",
        "categoria": "data",
        "titulo": "t",
        "causa": "c",
        "remediacao": "r",
    }
    entrada_sucesso = {
        "caminho": "api/db.py",
        "conteudo": 'conn.execute("CREATE TABLE x (id int)")\n',
        "regra": _regra_teste,
    }
    entrada_ok = {
        "caminho": "api/db.py",
        "conteudo": (
            "def init():\n    conn.execute('CREATE TABLE x (id int)')\n\ndef f():\n    pass\n"
        ),
        "regra": _regra_teste,
    }

    return CapabilityImplementation(
        definition=definicao,
        handler=avaliar_sec007,
        acceptance_tests=[
            AcceptanceTest(
                name="ddl-no-nivel-do-modulo-dispara-um-achado",
                entrada=entrada_sucesso,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: len(saida["achados"]) == 1,
            ),
            AcceptanceTest(
                name="ddl-dentro-de-funcao-nao-dispara",
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
