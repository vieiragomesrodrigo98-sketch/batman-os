"""Skill AST "nó selecionado sem padrão no corpo/contexto" (Vol.IV Cap.17).

Generaliza o padrão que se repete em BT-001, BT-002, BT-003, COMP-001,
COMP-002, EH-004 (achado de revisão da Milestone 3, ver plano de migração):
um nó AST é selecionado por um critério estrutural (nome de `ClassDef`,
decorator de `FunctionDef`, primeiro argumento literal de `Call`), e o
achado dispara quando o CORPO/CONTEXTO desse nó não casa um padrão de
"proteção" esperado (auditoria, autorização, campo de soft-delete, etc.).

Modos de seletor:
- `classdef`: casa pelo NOME da classe (`seletor_include`/`seletor_exclude`,
  regex). Corpo = `ast.get_source_segment(texto, node)`.
- `functiondef`: `seletor_include` casa em QUALQUER decorator
  (`ast.unparse(d)`) OU no corpo (`ast.get_source_segment(texto, node)` —
  que NÃO inclui os decorators, por isso os dois lados são checados por
  padrão; replica BT-002: `has_admin_dep` é decorator `Call` OU menção
  solta no corpo). `seletor_so_decorator=True` restringe a checagem só ao
  decorator (replica BT-001: `is_delete` só olha `node.decorator_list` —
  sem essa restrição, uma chamada `.delete(` solta no CORPO de qualquer
  função dispararia por engano). `seletor_exclude`, se casar em QUALQUER
  decorator, suprime o achado (replica BT-002: decorators de método
  read-only, ex. `@router.get`, excluem a regra). `seletor_nome_funcao`
  (achado de revisão da continuação da migração — DE-006/RISK-002),
  quando setado, seleciona SÓ pelo `node.name` (regex), substituindo
  inteiramente o mecanismo decorator/corpo-substring de `seletor_include`:
  necessário quando o legado seleciona a função pelo NOME
  especificamente (`re.search(padrao, node.name)`), não por menção solta
  em QUALQUER lugar do corpo — sem isso, uma função cujo corpo apenas
  MENCIONA a palavra-chave (ex.: chama outra função de nome parecido, ou
  tem um comentário) dispara por engano, mesmo não sendo ela própria a
  função-alvo.
- `call`: casa pelo PRIMEIRO ARGUMENTO literal de um `ast.Call` cujo
  `.func` é `Attribute` com nome em `metodos_call` (regex sobre o valor do
  literal). Corpo = janela de `janela_linhas` linhas após `node.lineno`
  (replica EH-004, que olha as próximas linhas do handler, não o
  `get_source_segment` do Call em si — um Call não tem "corpo" próprio).

Nos 3 modos de seletor acima, o corpo/contexto é comparado contra
`corpo_padrao` (regex) — por padrão, dispara achado se o corpo NÃO casar
esse padrão (ausência de proteção esperada). Campo opcional `corpo_escopo`
(regex) é um GATE positivo aplicado ao corpo ANTES de `corpo_padrao` — só
avalia `corpo_padrao` se `corpo_escopo` casar (replica COMP-001/COMP-002:
"tem campo de dado pessoal E não tem soft-delete", "tem campo cpf E não tem
mascaramento" — sem `corpo_escopo`, a regra dispararia para toda classe do
seletor, não só as que já contêm o dado sensível).

**Duas formas de semântica invertida** (achado dispara quando o padrão ESTÁ
presente, não ausente):
- `inverte_disparo: bool` — inverte o resultado de `corpo_padrao` (regex).
  Replica BT-003: campos `created_at`/`updated_at`/`id` presentes num schema
  de request já são o próprio risco (usuário manipula timestamps/IDs
  controlados pelo servidor), não a ausência de uma proteção.
- `campo_estrutural` — ativa um modo exato via `ast.AnnAssign`/`target.id`
  (replica EH-006, campo "role" editável), quando regex sobre
  `get_source_segment` não é preciso o bastante (precisa achar um campo
  declarado de verdade, não uma menção em comentário/docstring). Ignora
  `corpo_padrao`/`corpo_escopo`/`inverte_disparo` quando setado.
"""

from __future__ import annotations

import ast
import re
from enum import StrEnum
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


class SeletorTipo(StrEnum):
    CLASSDEF = "classdef"
    FUNCTIONDEF = "functiondef"
    CALL = "call"


class RegraAstSpec(BaseModel):
    """Espelha `RegraSpec` (regex_sobre_conteudo.py) — mesmos campos de
    julgamento embutido, só a lógica de detecção é estrutural (AST)."""

    codigo: str
    agente: str
    severidade: str
    categoria: str
    titulo: str
    causa: str
    remediacao: str
    seletor_tipo: SeletorTipo
    seletor_include: str
    seletor_exclude: str | None = None
    seletor_so_decorator: bool = False
    seletor_nome_funcao: str | None = None
    corpo_padrao: str
    corpo_escopo: str | None = None
    inverte_disparo: bool = False
    campo_estrutural: str | None = None
    metodos_call: list[str] = Field(default_factory=list)
    janela_linhas: int = 10
    precondicao_arquivo: str | None = None
    ignore_case: bool = False


class EntradaAst(BaseModel):
    """`tipo` é um discriminador estrutural puro: `CapabilityRegistry.
    find_candidates` (Vol.III Cap.11) casa por presença de CHAVES de
    top-level do schema em `intent.dados`, não por tipo/shape profundo. Sem
    esta chave extra (ausente em `EntradaRegexArquivo`), uma Missão com
    entrada de REGEX (que tem `condicoes_adicionais` a mais) ainda casaria
    "por engano" como candidata a esta Capability, já que suas 3 chaves
    (`caminho`/`conteudo`/`regra`) seriam um subconjunto válido — 2
    Capabilities candidatas para 1 intent, quando só uma faz sentido."""

    tipo: Literal["ast"] = "ast"
    caminho: str
    conteudo: str | None = None
    regra: RegraAstSpec


class AchadoAst(BaseModel):
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


class SaidaAst(BaseModel):
    achados: list[AchadoAst] = Field(default_factory=list)


class EntradaInvalida(Exception):
    """Levantada quando `entrada` não satisfaz `EntradaAst` ou o conteúdo
    tem erro de sintaxe Python — vira SCHEMA_REJECTION/falha de invocação
    no Execution Engine (Vol.III Cap.12)."""


def _computar_fingerprint(
    agente: str, categoria: str, caminho: str, codigo: str, chave: str = ""
) -> str:
    import hashlib

    normalizado = caminho.replace("\\", "/")
    bruto = f"{agente}|{categoria}|{normalizado}|{codigo}|{chave}"
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()


def _dispara_por_corpo(corpo: str, regra: RegraAstSpec) -> bool:
    """`campo_estrutural` (modo exato via `ast.AnnAssign`, caso EH-006) é
    verificado por `_tem_campo_estrutural` antes de chegar aqui — esta
    função só avalia o modo regex sobre `corpo`/contexto.

    `corpo_escopo` é um gate positivo: se setado e não casar, a regra nem
    chega a avaliar `corpo_padrao` (replica COMP-001/COMP-002 — só avalia
    ausência de soft-delete/mascaramento em classes que JÁ têm o dado
    sensível)."""
    flags = re.IGNORECASE if regra.ignore_case else 0
    if regra.corpo_escopo and not re.search(regra.corpo_escopo, corpo, flags):
        return False
    casou = re.search(regra.corpo_padrao, corpo, flags) is not None
    return casou if regra.inverte_disparo else not casou


def _tem_campo_estrutural(node: ast.ClassDef, nome_campo: str) -> bool:
    for item in node.body:
        if (
            isinstance(item, ast.AnnAssign)
            and isinstance(item.target, ast.Name)
            and item.target.id == nome_campo
        ):
            return True
    return False


def _avaliar_classdef(tree: ast.AST, texto: str, regra: RegraAstSpec) -> bool:
    flags = re.IGNORECASE if regra.ignore_case else 0
    include_rx = re.compile(regra.seletor_include, flags)
    exclude_rx = re.compile(regra.seletor_exclude, flags) if regra.seletor_exclude else None

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if exclude_rx and exclude_rx.search(node.name):
            continue
        if not include_rx.search(node.name):
            continue
        if regra.campo_estrutural:
            # inverso dos demais modos: aqui disparo = campo INDESEJADO
            # presente (ex.: EH-006 — campo "role" editavel num schema de
            # update é o proprio risco, nao a ausencia de protecao).
            if _tem_campo_estrutural(node, regra.campo_estrutural):
                return True
            continue
        corpo = ast.get_source_segment(texto, node) or ""
        if _dispara_por_corpo(corpo, regra):
            return True
    return False


def _decorator_texto(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def _avaliar_functiondef(tree: ast.AST, texto: str, regra: RegraAstSpec) -> bool:
    flags = re.IGNORECASE if regra.ignore_case else 0
    include_rx = re.compile(regra.seletor_include, flags)
    exclude_rx = re.compile(regra.seletor_exclude, flags) if regra.seletor_exclude else None
    nome_rx = re.compile(regra.seletor_nome_funcao, flags) if regra.seletor_nome_funcao else None

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        decoradores = [_decorator_texto(d) for d in node.decorator_list]
        corpo = ast.get_source_segment(texto, node) or ""
        if nome_rx is not None:
            # seletor_nome_funcao: seleciona SO pelo node.name — substitui
            # inteiramente o mecanismo decorator/corpo-substring abaixo
            # (necessario quando o legado seleciona por nome de funcao
            # especificamente, nao por mencao solta em qualquer lugar do
            # corpo; ver DE-006/RISK-002).
            selecionado = bool(nome_rx.search(node.name))
        else:
            # seletor_include casa no decorator OU no corpo por padrao (replica
            # BT-002: `has_admin_dep` é decorator Call OU menção solta no corpo
            # da funcao — `ast.get_source_segment` de FunctionDef NAO inclui os
            # decorators, entao os dois lados precisam ser checados).
            # `seletor_so_decorator=True` restringe so ao decorator (replica
            # BT-001: `is_delete` so olha `node.decorator_list`, nunca o corpo —
            # sem essa restricao, uma chamada `.delete(` solta no CORPO de
            # qualquer funcao dispararia a regra por engano).
            selecionado = any(include_rx.search(d) for d in decoradores)
            if not selecionado and not regra.seletor_so_decorator:
                selecionado = bool(include_rx.search(corpo))
        if not selecionado:
            continue
        if exclude_rx and any(exclude_rx.search(d) for d in decoradores):
            continue
        if _dispara_por_corpo(corpo, regra):
            return True
    return False


def _avaliar_call(tree: ast.AST, texto: str, regra: RegraAstSpec) -> bool:
    flags = re.IGNORECASE if regra.ignore_case else 0
    include_rx = re.compile(regra.seletor_include, flags)
    linhas = texto.splitlines()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in regra.metodos_call:
            continue
        if not node.args or not isinstance(node.args[0], ast.Constant):
            continue
        valor = str(node.args[0].value)
        if not include_rx.search(valor):
            continue
        janela = "\n".join(linhas[node.lineno : node.lineno + regra.janela_linhas])
        contexto = _decorator_texto(node) + "\n" + janela
        if _dispara_por_corpo(contexto, regra):
            return True
    return False


def avaliar_regra_ast(entrada: Any, contexto: ExecutionContext) -> Any:
    """Vol.IV Cap.17 — handler puro: recebe o texto já lido, faz `ast.parse`
    internamente (parsing não é IO, é análise sobre texto já carregado —
    mesmo espírito de handler puro da Skill regex)."""
    del contexto
    try:
        dados = EntradaAst.model_validate(entrada)
    except Exception as exc:
        raise EntradaInvalida(str(exc)) from exc

    if dados.conteudo is None:
        return SaidaAst(achados=[]).model_dump()

    try:
        tree = ast.parse(dados.conteudo)
    except SyntaxError:
        return SaidaAst(achados=[]).model_dump()

    regra = dados.regra
    if regra.precondicao_arquivo:
        flags = re.IGNORECASE if regra.ignore_case else 0
        if not re.search(regra.precondicao_arquivo, dados.conteudo, flags):
            return SaidaAst(achados=[]).model_dump()

    if regra.seletor_tipo == SeletorTipo.CLASSDEF:
        disparado = _avaliar_classdef(tree, dados.conteudo, regra)
    elif regra.seletor_tipo == SeletorTipo.FUNCTIONDEF:
        disparado = _avaliar_functiondef(tree, dados.conteudo, regra)
    else:
        disparado = _avaliar_call(tree, dados.conteudo, regra)

    if not disparado:
        return SaidaAst(achados=[]).model_dump()

    fingerprint = _computar_fingerprint(regra.agente, regra.categoria, dados.caminho, regra.codigo)
    achado = AchadoAst(
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
    return SaidaAst(achados=[achado]).model_dump()


def construir_implementacao() -> CapabilityImplementation:
    definicao = CapabilityDefinition(
        id=CapabilityId("ast-no-selecionado-sem-padrao"),
        name="AST: no selecionado sem padrao no corpo/contexto",
        version="1.0.0",
        input_schema=EntradaAst.model_json_schema(),
        output_schema=SaidaAst.model_json_schema(),
        deterministic=True,
        side_effects=SideEffects.NONE,
        idempotent=True,
    )

    entrada_sucesso = {
        "caminho": "a.py",
        "conteudo": "class FooRequest:\n    id: int\n",
        "regra": {
            "codigo": "TEST-AST-001",
            "agente": "teste",
            "severidade": "high",
            "categoria": "teste",
            "titulo": "teste",
            "causa": "teste",
            "remediacao": "teste",
            "seletor_tipo": "classdef",
            "seletor_include": "Request$",
            "corpo_padrao": "protegido",
        },
    }
    entrada_erro_sintaxe = {
        "caminho": "a.py",
        "conteudo": "def (:\n",
        "regra": {
            "codigo": "TEST-AST-002",
            "agente": "teste",
            "severidade": "high",
            "categoria": "teste",
            "titulo": "teste",
            "causa": "teste",
            "remediacao": "teste",
            "seletor_tipo": "classdef",
            "seletor_include": "Request$",
            "corpo_padrao": "protegido",
        },
    }
    entrada_regex_malformado = {
        "caminho": "a.py",
        "conteudo": "class FooRequest:\n    id: int\n",
        "regra": {
            "codigo": "TEST-AST-003",
            "agente": "teste",
            "severidade": "high",
            "categoria": "teste",
            "titulo": "teste",
            "causa": "teste",
            "remediacao": "teste",
            "seletor_tipo": "classdef",
            "seletor_include": "(",  # regex malformado -> re.error, tratado como falha de invocacao
            "corpo_padrao": "protegido",
        },
    }

    return CapabilityImplementation(
        definition=definicao,
        handler=avaliar_regra_ast,
        acceptance_tests=[
            AcceptanceTest(
                name="classdef-sem-padrao-dispara",
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
                name="seletor-regex-malformado-e-tratado-como-falha-de-invocacao",
                entrada=entrada_regex_malformado,
                resultado_esperado=ResultadoEsperado.TIMEOUT,
            ),
        ],
    )
