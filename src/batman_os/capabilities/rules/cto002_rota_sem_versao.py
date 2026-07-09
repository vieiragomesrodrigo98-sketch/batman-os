"""Capability bespoke CTO-002 "rota de API sem prefixo de versão"
(Vol.IV Cap.17).

Não generalizada em `ast_kwarg_ausente.py` apesar da semelhança
estrutural (mesmo seletor `Call` com `func=Attribute` e `.attr` em HTTP
methods) — aqui a condição de disparo VALIDA O VALOR do primeiro
argumento literal contra um regex + lista de exceções, não checa
ausência de kwarg. Forma diferente o bastante para não valer generalizar
a Skill (única ocorrência conhecida deste padrão)."""

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

_HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete"})
_VERSAO_RE = re.compile(r"^/v\d+/")
_ROTAS_EXCECAO = frozenset({"/", "/health", "/docs", "/openapi.json"})


class RegraCto002Spec(BaseModel):
    codigo: str
    agente: str
    severidade: str
    categoria: str
    titulo: str
    causa: str
    remediacao: str


class EntradaCto002(BaseModel):
    tipo: Literal["cto002"] = "cto002"
    caminho: str
    conteudo: str | None = None
    regra: RegraCto002Spec


class AchadoCto002(BaseModel):
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


class SaidaCto002(BaseModel):
    achados: list[AchadoCto002] = Field(default_factory=list)


class EntradaInvalida(Exception):
    """Levantada quando `entrada` não satisfaz `EntradaCto002` — vira
    SCHEMA_REJECTION no Execution Engine (Vol.III Cap.12)."""


def _computar_fingerprint(agente: str, categoria: str, caminho: str, codigo: str) -> str:
    import hashlib

    normalizado = caminho.replace("\\", "/")
    bruto = f"{agente}|{categoria}|{normalizado}|{codigo}|"
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()


def avaliar_cto002(entrada: Any, contexto: ExecutionContext) -> Any:
    del contexto
    try:
        dados = EntradaCto002.model_validate(entrada)
    except Exception as exc:
        raise EntradaInvalida(str(exc)) from exc

    if dados.conteudo is None:
        return SaidaCto002(achados=[]).model_dump()

    try:
        tree = ast.parse(dados.conteudo)
    except SyntaxError:
        return SaidaCto002(achados=[]).model_dump()

    dispara = False
    linha = 0
    rota = ""
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _HTTP_METHODS
        ):
            continue
        if not node.args or not isinstance(node.args[0], ast.Constant):
            continue
        path = node.args[0].value
        if not isinstance(path, str):
            continue
        if not _VERSAO_RE.match(path) and path not in _ROTAS_EXCECAO:
            dispara = True
            linha = node.lineno
            rota = path
            break

    if not dispara:
        return SaidaCto002(achados=[]).model_dump()

    regra = dados.regra
    fingerprint = _computar_fingerprint(regra.agente, regra.categoria, dados.caminho, regra.codigo)
    achado = AchadoCto002(
        codigo=regra.codigo,
        agente=regra.agente,
        severidade=regra.severidade,
        categoria=regra.categoria,
        titulo=regra.titulo,
        descricao=f"{dados.caminho}: rota `{rota}` sem prefixo /v{{n}}/ (linha {linha}).",
        causa=regra.causa,
        remediacao=regra.remediacao,
        arquivo=dados.caminho,
        fingerprint=fingerprint,
    )
    return SaidaCto002(achados=[achado]).model_dump()


def construir_implementacao() -> CapabilityImplementation:
    definicao = CapabilityDefinition(
        id=CapabilityId("cto002-rota-sem-versao"),
        name="CTO-002 rota de API sem prefixo de versao",
        version="1.0.0",
        input_schema=EntradaCto002.model_json_schema(),
        output_schema=SaidaCto002.model_json_schema(),
        deterministic=True,
        side_effects=SideEffects.NONE,
        idempotent=True,
    )

    _regra_teste = {
        "codigo": "CTO-002",
        "agente": "cto",
        "severidade": "medium",
        "categoria": "api-design",
        "titulo": "t",
        "causa": "c",
        "remediacao": "r",
    }
    entrada_sucesso = {
        "caminho": "api/routers/pedidos.py",
        "conteudo": "@router.get('/pedidos')\ndef listar():\n    pass\n",
        "regra": _regra_teste,
    }
    entrada_ok = {
        "caminho": "api/routers/pedidos.py",
        "conteudo": "@router.get('/v1/pedidos')\ndef listar():\n    pass\n",
        "regra": _regra_teste,
    }

    return CapabilityImplementation(
        definition=definicao,
        handler=avaliar_cto002,
        acceptance_tests=[
            AcceptanceTest(
                name="rota-sem-versao-dispara",
                entrada=entrada_sucesso,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: len(saida["achados"]) == 1,
            ),
            AcceptanceTest(
                name="rota-com-versao-nao-dispara",
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
                    "caminho": "api/routers/x.py",
                    "conteudo": "x",
                    "regra": {"severidade": 123},
                },
                resultado_esperado=ResultadoEsperado.TIMEOUT,
            ),
        ],
    )
