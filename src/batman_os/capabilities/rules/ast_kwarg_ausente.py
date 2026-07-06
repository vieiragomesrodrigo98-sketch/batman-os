"""Skill AST "Call com kwarg obrigatório ausente" (Vol.IV Cap.17).

Segunda Skill AST da Milestone 3 — mais restrita que
`ast_padrao_ausente.py`: aqui o achado não depende de corpo/contexto, só da
PRÓPRIA chamada. Cobre CTO-001 (`ExternalCallWithoutTimeout`): toda chamada
`.get(/.post(/.../.request(` num objeto `requests`/`httpx`/`*.client`/
`*.session` que não passa `timeout=` dispara achado.

`objeto_attr_permitido`/`objeto_name_permitido` replicam o filtro de
"objeto-base" do legado (`node.func.value` é `Attribute` com nome em
`{"client","session"}` OU `Name` com nome em `{"requests","httpx"}`) — se
ambos vazios, qualquer objeto-base é aceito (nenhum código migrado precisa
disso ainda, mas evita reescrever a Skill se aparecer um caso sem esse
filtro).
"""

from __future__ import annotations

import ast
import hashlib
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


class RegraKwargAusenteSpec(BaseModel):
    codigo: str
    agente: str
    severidade: str
    categoria: str
    titulo: str
    causa: str
    remediacao: str
    metodos_call: list[str]
    kwarg_obrigatorio: str
    objeto_attr_permitido: list[str] = Field(default_factory=list)
    objeto_name_permitido: list[str] = Field(default_factory=list)


class EntradaKwargAusente(BaseModel):
    """`tipo` é o mesmo discriminador estrutural de `EntradaAst.tipo`
    (`ast_padrao_ausente.py`) — evita que `CapabilityRegistry.find_candidates`
    (casamento por chaves de schema) confunda esta Capability com as
    outras duas já registradas."""

    tipo: Literal["ast-kwarg-ausente"] = "ast-kwarg-ausente"
    caminho: str
    conteudo: str | None = None
    regra: RegraKwargAusenteSpec


class AchadoKwargAusente(BaseModel):
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


class SaidaKwargAusente(BaseModel):
    achados: list[AchadoKwargAusente] = Field(default_factory=list)


class EntradaInvalida(Exception):
    """Levantada quando `entrada` não satisfaz `EntradaKwargAusente` — vira
    SCHEMA_REJECTION no Execution Engine (Vol.III Cap.12)."""


def _computar_fingerprint(agente: str, categoria: str, caminho: str, codigo: str) -> str:
    normalizado = caminho.replace("\\", "/")
    bruto = f"{agente}|{categoria}|{normalizado}|{codigo}|"
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()


def _objeto_bate(node_func_value: ast.expr, regra: RegraKwargAusenteSpec) -> bool:
    if not regra.objeto_attr_permitido and not regra.objeto_name_permitido:
        return True
    bate_attr = (
        isinstance(node_func_value, ast.Attribute)
        and node_func_value.attr in regra.objeto_attr_permitido
    )
    bate_name = (
        isinstance(node_func_value, ast.Name) and node_func_value.id in regra.objeto_name_permitido
    )
    return bate_attr or bate_name


def _dispara(tree: ast.AST, regra: RegraKwargAusenteSpec) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in regra.metodos_call:
            continue
        if not _objeto_bate(node.func.value, regra):
            continue
        kw_names = {kw.arg for kw in node.keywords}
        if regra.kwarg_obrigatorio not in kw_names:
            return True
    return False


def avaliar_regra_kwarg_ausente(entrada: Any, contexto: ExecutionContext) -> Any:
    """Vol.IV Cap.17 — handler puro: recebe o texto já lido, faz `ast.parse`
    internamente."""
    del contexto
    try:
        dados = EntradaKwargAusente.model_validate(entrada)
    except Exception as exc:
        raise EntradaInvalida(str(exc)) from exc

    if dados.conteudo is None:
        return SaidaKwargAusente(achados=[]).model_dump()

    try:
        tree = ast.parse(dados.conteudo)
    except SyntaxError:
        return SaidaKwargAusente(achados=[]).model_dump()

    regra = dados.regra
    if not _dispara(tree, regra):
        return SaidaKwargAusente(achados=[]).model_dump()

    fingerprint = _computar_fingerprint(regra.agente, regra.categoria, dados.caminho, regra.codigo)
    achado = AchadoKwargAusente(
        codigo=regra.codigo,
        agente=regra.agente,
        severidade=regra.severidade,
        categoria=regra.categoria,
        titulo=regra.titulo,
        descricao=f"{dados.caminho}: {regra.titulo}",
        causa=regra.causa,
        remediacao=regra.remediacao,
        arquivo=dados.caminho,
        fingerprint=fingerprint,
    )
    return SaidaKwargAusente(achados=[achado]).model_dump()


def construir_implementacao() -> CapabilityImplementation:
    definicao = CapabilityDefinition(
        id=CapabilityId("ast-call-kwarg-ausente"),
        name="AST: Call com kwarg obrigatorio ausente",
        version="1.0.0",
        input_schema=EntradaKwargAusente.model_json_schema(),
        output_schema=SaidaKwargAusente.model_json_schema(),
        deterministic=True,
        side_effects=SideEffects.NONE,
        idempotent=True,
    )

    regra_teste = {
        "codigo": "TEST-KW-001",
        "agente": "teste",
        "severidade": "high",
        "categoria": "teste",
        "titulo": "teste",
        "causa": "teste",
        "remediacao": "teste",
        "metodos_call": ["get", "post"],
        "kwarg_obrigatorio": "timeout",
        "objeto_name_permitido": ["requests"],
    }
    entrada_sucesso = {
        "caminho": "a.py",
        "conteudo": "requests.get('http://x')\n",
        "regra": regra_teste,
    }
    entrada_erro_sintaxe = {"caminho": "a.py", "conteudo": "def (:\n", "regra": regra_teste}
    entrada_regra_invalida = {
        "caminho": "a.py",
        "conteudo": "x = 1\n",
        "regra": {**regra_teste, "metodos_call": "nao-e-uma-lista"},
    }

    return CapabilityImplementation(
        definition=definicao,
        handler=avaliar_regra_kwarg_ausente,
        acceptance_tests=[
            AcceptanceTest(
                name="call-sem-kwarg-obrigatorio-dispara",
                entrada=entrada_sucesso,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: len(saida["achados"]) == 1,
            ),
            AcceptanceTest(
                name="entrada-sem-campo-obrigatorio-e-rejeitada",
                entrada={"caminho": "a.py"},
                resultado_esperado=ResultadoEsperado.SCHEMA_REJECTION,
            ),
            AcceptanceTest(
                name="erro-de-sintaxe-nao-quebra-o-handler",
                entrada=entrada_erro_sintaxe,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: saida["achados"] == [],
            ),
            AcceptanceTest(
                name="regra-com-tipo-de-campo-invalido-e-tratada-como-falha-de-invocacao",
                entrada=entrada_regra_invalida,
                resultado_esperado=ResultadoEsperado.TIMEOUT,
            ),
        ],
    )
