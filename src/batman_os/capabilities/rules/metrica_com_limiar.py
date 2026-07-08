"""Skill "métrica com limiar" (Vol.IV Cap.17).

Generaliza o padrão que se repete em 7 códigos da continuação da migração
(REV-001, REV-002, REV-003, REV-004, SD-011, UXR-001, CTO-005): computar
uma MÉTRICA NUMÉRICA sobre o arquivo (contagem de linhas, contagem de
ocorrências de um padrão, quantidade de parâmetros de função, profundidade
de indentação) e disparar achado se ultrapassa um limiar.

Modos de métrica (`RegraMetricaSpec.metrica`):
- `linhas_arquivo`: `len(texto.splitlines())` — replica REV-001.
- `contagem_ocorrencias`: `len(re.findall(pattern, texto))` — replica
  SD-011/UXR-001. `pattern_excecao_arquivo` (opcional) suprime o achado se
  casar em QUALQUER lugar do arquivo (replica o gate `has_grouping` de
  UXR-001 — agrupamento visual presente neutraliza a contagem de campos).
- `contagem_padroes_distintos`: quantos padrões de `padroes` (lista) casam
  ao menos uma vez no texto — replica CTO-005 (quantos "domínios"
  distintos aparecem nos imports). `pattern_filtro_linhas` (opcional)
  filtra o texto para só as linhas que casam esse padrão ANTES de contar
  (replica CTO-005: só considera linhas de import).
- `linhas_funcao`: para cada FunctionDef/AsyncFunctionDef, `end_lineno -
  lineno + 1` — replica REV-002.
- `parametros_funcao`: para cada FunctionDef/AsyncFunctionDef, conta de
  parâmetros (posonly+args+kwonly, excluindo self/cls) — replica REV-003.
- `col_offset_maximo`: para cada `ast.stmt`, `node.col_offset` — replica
  REV-004 (profundidade de indentação, 4 espaços por nível).

Nos 3 modos AST (`linhas_funcao`/`parametros_funcao`/`col_offset_maximo`),
MÚLTIPLAS ocorrências no mesmo arquivo colapsam num único achado agregado
(`chave` vazia, mesmo fingerprint independente de quantos nós excedem o
limiar — mesma equivalência já estabelecida para BE-006/MOB-003/EH-009 no
comparativo de fingerprint: o legado às vezes `yield`a por ocorrência, mas
sem `chave` todas colapsam no mesmo fingerprint de qualquer forma).

`operador` (`>` ou `>=`) — a maioria dos códigos usa "> limiar" (REV-001/
002/003/004, UXR-001), CTO-005 usa ">= limiar" (>=6 domínios)."""

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


class MetricaTipo(StrEnum):
    LINHAS_ARQUIVO = "linhas_arquivo"
    CONTAGEM_OCORRENCIAS = "contagem_ocorrencias"
    CONTAGEM_PADROES_DISTINTOS = "contagem_padroes_distintos"
    LINHAS_FUNCAO = "linhas_funcao"
    PARAMETROS_FUNCAO = "parametros_funcao"
    COL_OFFSET_MAXIMO = "col_offset_maximo"


class RegraMetricaSpec(BaseModel):
    codigo: str
    agente: str
    severidade: str
    categoria: str
    titulo: str
    causa: str
    remediacao: str
    metrica: MetricaTipo
    limiar: int
    operador: Literal[">", ">="] = ">"
    pattern: str | None = None
    padroes: list[str] = Field(default_factory=list)
    pattern_filtro_linhas: str | None = None
    pattern_excecao_arquivo: str | None = None
    ignore_case: bool = False


class EntradaMetrica(BaseModel):
    """`tipo` é o mesmo discriminador estrutural das outras Entradas desta
    migração (ver nota em `EntradaAgregada`)."""

    tipo: Literal["metrica-limiar"] = "metrica-limiar"
    caminho: str
    conteudo: str | None = None
    regra: RegraMetricaSpec


class AchadoMetrica(BaseModel):
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


class SaidaMetrica(BaseModel):
    achados: list[AchadoMetrica] = Field(default_factory=list)


class EntradaInvalida(Exception):
    """Levantada quando `entrada` não satisfaz `EntradaMetrica` — vira
    SCHEMA_REJECTION no Execution Engine (Vol.III Cap.12)."""


def _computar_fingerprint(agente: str, categoria: str, caminho: str, codigo: str) -> str:
    import hashlib

    normalizado = caminho.replace("\\", "/")
    bruto = f"{agente}|{categoria}|{normalizado}|{codigo}|"
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()


def _dispara(valor: int, limiar: int, operador: str) -> bool:
    return valor >= limiar if operador == ">=" else valor > limiar


def _params_sem_self_cls(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    a = node.args
    params = list(a.posonlyargs) + list(a.args) + list(a.kwonlyargs)
    return [arg.arg for arg in params if arg.arg not in ("self", "cls")]


def _calcular_metrica(texto: str, regra: RegraMetricaSpec) -> int | None:
    """Retorna a métrica agregada (máximo entre ocorrências, para os modos
    AST-por-nó) ou None se o modo exige AST e o texto não parseia."""
    flags = re.IGNORECASE if regra.ignore_case else 0

    if regra.metrica == MetricaTipo.LINHAS_ARQUIVO:
        return len(texto.splitlines())

    if regra.metrica == MetricaTipo.CONTAGEM_OCORRENCIAS:
        if regra.pattern_excecao_arquivo and re.search(regra.pattern_excecao_arquivo, texto, flags):
            return 0
        return len(re.findall(regra.pattern or "", texto, flags))

    if regra.metrica == MetricaTipo.CONTAGEM_PADROES_DISTINTOS:
        alvo = texto
        if regra.pattern_filtro_linhas:
            filtro_rx = re.compile(regra.pattern_filtro_linhas, flags)
            alvo = "\n".join(ln for ln in texto.splitlines() if filtro_rx.search(ln))
        return sum(1 for padrao in regra.padroes if re.search(padrao, alvo, flags))

    try:
        tree = ast.parse(texto)
    except SyntaxError:
        return None

    if regra.metrica == MetricaTipo.LINHAS_FUNCAO:
        maximo = 0
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fim = getattr(node, "end_lineno", node.lineno) or node.lineno
                maximo = max(maximo, fim - node.lineno + 1)
        return maximo

    if regra.metrica == MetricaTipo.PARAMETROS_FUNCAO:
        maximo = 0
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                maximo = max(maximo, len(_params_sem_self_cls(node)))
        return maximo

    if regra.metrica == MetricaTipo.COL_OFFSET_MAXIMO:
        maximo = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.stmt):
                maximo = max(maximo, node.col_offset)
        return maximo

    return None


def avaliar_regra_metrica(entrada: Any, contexto: ExecutionContext) -> Any:
    del contexto
    try:
        dados = EntradaMetrica.model_validate(entrada)
    except Exception as exc:
        raise EntradaInvalida(str(exc)) from exc

    regra = dados.regra
    texto = dados.conteudo or ""
    valor = _calcular_metrica(texto, regra)

    if valor is None or not _dispara(valor, regra.limiar, regra.operador):
        return SaidaMetrica(achados=[]).model_dump()

    fingerprint = _computar_fingerprint(regra.agente, regra.categoria, dados.caminho, regra.codigo)
    achado = AchadoMetrica(
        codigo=regra.codigo,
        agente=regra.agente,
        severidade=regra.severidade,
        categoria=regra.categoria,
        titulo=regra.titulo,
        descricao=f"{dados.caminho}: {regra.titulo} ({valor}, limiar {regra.limiar}).",
        causa=regra.causa,
        remediacao=regra.remediacao,
        arquivo=dados.caminho,
        fingerprint=fingerprint,
    )
    return SaidaMetrica(achados=[achado]).model_dump()


def construir_implementacao() -> CapabilityImplementation:
    definicao = CapabilityDefinition(
        id=CapabilityId("metrica-com-limiar"),
        name="Metrica com limiar",
        version="1.0.0",
        input_schema=EntradaMetrica.model_json_schema(),
        output_schema=SaidaMetrica.model_json_schema(),
        deterministic=True,
        side_effects=SideEffects.NONE,
        idempotent=True,
    )

    entrada_sucesso = {
        "caminho": "a.py",
        "conteudo": "\n".join(f"linha{i}" for i in range(10)),
        "regra": {
            "codigo": "TEST-MET-001",
            "agente": "teste",
            "severidade": "high",
            "categoria": "teste",
            "titulo": "teste",
            "causa": "teste",
            "remediacao": "teste",
            "metrica": "linhas_arquivo",
            "limiar": 5,
        },
    }
    entrada_regex_malformado = {
        "caminho": "a.py",
        "conteudo": "x",
        "regra": {
            "codigo": "TEST-MET-002",
            "agente": "teste",
            "severidade": "high",
            "categoria": "teste",
            "titulo": "teste",
            "causa": "teste",
            "remediacao": "teste",
            "metrica": "contagem_ocorrencias",
            "pattern": "(",
            "limiar": 0,
        },
    }

    return CapabilityImplementation(
        definition=definicao,
        handler=avaliar_regra_metrica,
        acceptance_tests=[
            AcceptanceTest(
                name="metrica-acima-do-limiar-dispara-um-achado",
                entrada=entrada_sucesso,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: len(saida["achados"]) == 1,
            ),
            AcceptanceTest(
                name="entrada-sem-campo-obrigatorio-e-rejeitada",
                entrada={"caminho": "a.py"},  # falta 'regra'
                resultado_esperado=ResultadoEsperado.SCHEMA_REJECTION,
            ),
            AcceptanceTest(
                name="pattern-malformado-e-tratado-como-falha-de-invocacao",
                entrada=entrada_regex_malformado,
                resultado_esperado=ResultadoEsperado.TIMEOUT,
            ),
        ],
    )
