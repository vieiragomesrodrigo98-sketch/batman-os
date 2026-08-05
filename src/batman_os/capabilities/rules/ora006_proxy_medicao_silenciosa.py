"""Capability bespoke ORA-006 "medição falha (None) trocada por proxy
calculado, sem log" (Vol.IV Cap.17).

Replica `Batman/scan/rules/oracle.py::SilentMeasurementProxy`: `x = None`
como "não consegui medir" é contrato legítimo e comum; o que NÃO é legítimo
é o chamador substituir a medição que falhou por uma OUTRA CONTA (um proxy)
sem registrar que fez isso. Uma constante default (`x = 0`) é visível na
revisão; um proxy calculado é indistinguível do valor real depois de
gravado no banco — foi exatamente assim que o MFE/MAE do day trade passou
meses sendo o `exit_reason` disfarçado de medição (S142).

Mesmo padrão da bespoke ORA-005 (análise POR ARQUIVO, descoberta `"arvore"`
já existente, handler AST puro) — `_LOG_ATTRS`/`_walk_handler` são
duplicados de `ora005_fallback_silencioso.py` deliberadamente, mantendo
cada módulo de Capability autocontido (nenhum importa helper privado de
outro)."""

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

AGENTE = "oracle"
CATEGORIA = "codigo-morto"
CODIGO = "ORA-006"

_LOG_ATTRS = {"debug", "info", "warning", "warn", "error", "exception", "critical", "log"}

_LOOKUP_ATTRS = {  # "não achei no banco" ≠ "não consegui medir"
    "first",
    "one_or_none",
    "scalar",
    "scalar_one_or_none",
    "get",
    "getenv",
    "getattr",
}


class RegraOra006Spec(BaseModel):
    codigo: str = CODIGO
    agente: str = AGENTE
    severidade: str = "high"
    categoria: str = CATEGORIA
    titulo: str = "medição que falhou (None) é trocada por proxy calculado, sem log"
    causa: str = (
        "O mecanismo da S142: `measure_excursions()` devolve None quando falta "
        "barra de preço, e `build_outcome()` cai num PROXY derivado do "
        "`exit_reason` — sem log. O outcome é escrito UMA vez, então o proxy "
        "vira permanente: MFE/MAE ficaram errados em 107 de 136 outcomes e a "
        "Regra 4 do CLAUDE.md foi violada em silêncio por meses, alimentando a "
        "autocalibragem com número inventado. É a morte silenciosa da ORA-005 "
        "SEM exceção nenhuma — nenhum except para o Batman enxergar. "
        "Constante default (`x = 0`) é visível na revisão; proxy calculado é "
        "indistinguível do valor real depois de gravado."
    )
    remediacao: str = (
        "Registre a degradação: logue que a medição falhou e que um proxy foi "
        "usado, e — se o valor for persistido — grave a PROCEDÊNCIA junto "
        "(ex.: coluna `fonte='proxy'`), para que o consumidor possa descartá-lo. "
        "O proxy pode continuar existindo; o que não pode é ser INVISÍVEL a "
        "jusante. DoD: todo fallback de medição loga, e todo valor persistido "
        "sabe dizer se foi medido ou inferido."
    )


class EntradaOra006(BaseModel):
    """`tipo` é o mesmo discriminador estrutural usado em todas as Entradas
    desta migração (ver docstring de `EntradaAst.tipo`)."""

    tipo: Literal["ora006"] = "ora006"
    caminho: str
    conteudo: str | None = None
    regra: RegraOra006Spec = Field(default_factory=RegraOra006Spec)


class AchadoOra006(BaseModel):
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


class SaidaOra006(BaseModel):
    achados: list[AchadoOra006] = Field(default_factory=list)


class EntradaInvalida(Exception):
    """Levantada quando `entrada` não satisfaz `EntradaOra006` — vira
    SCHEMA_REJECTION no Execution Engine (Vol.III Cap.12)."""


def _computar_fingerprint(caminho: str, chave: str) -> str:
    normalizado = caminho.replace("\\", "/")
    bruto = f"{AGENTE}|{CATEGORIA}|{normalizado}|{CODIGO}|{chave}"
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()


def _eh_construtor(f: ast.expr) -> bool:
    """`Tabela(...)` — instanciação, não proxy. Mata o padrão get-or-create."""
    nome = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else "")
    return bool(nome) and nome[0].isupper()


def _eh_medicao(node: ast.expr | None) -> bool:
    """Chamada que MEDE algo — exclui lookup de ORM/config e construtor."""
    if not isinstance(node, ast.Call):
        return False
    f = node.func
    if isinstance(f, ast.Attribute) and f.attr in _LOOKUP_ATTRS:
        return False
    if isinstance(f, ast.Name) and f.id in _LOOKUP_ATTRS:
        return False
    return not _eh_construtor(f)


def _valor_fabricado(node: ast.expr | None) -> bool:
    """
    Valor DERIVADO de outros dados — o que torna o proxy perigoso.

    Constante (`x = 0`, `x = None`) é sentinela: visível na revisão e o
    consumidor costuma saber distinguir. Já uma CONTA (`mfe = tgt - entry`,
    `max(...)`, `a if c else b`) fabrica um número plausível, indistinguível
    da medição real depois de gravado. Construtor é instanciação, não proxy.
    """
    if isinstance(node, ast.Call):
        return not _eh_construtor(node.func)
    return isinstance(node, (ast.BinOp, ast.IfExp))


def _guarda_de_falha(test: ast.expr) -> tuple[str, bool] | None:
    """
    (nome, fallback_no_else) para os 4 formatos de guarda de falha:
      `if x is None:` / `if not x:`      -> fallback no CORPO
      `if x is not None:` / `if x:`      -> fallback no ELSE
    """
    if isinstance(test, ast.Compare) and len(test.ops) == 1 and len(test.comparators) == 1:
        cmp = test.comparators[0]
        if isinstance(cmp, ast.Constant) and cmp.value is None and isinstance(test.left, ast.Name):
            if isinstance(test.ops[0], ast.Is):
                return test.left.id, False
            if isinstance(test.ops[0], ast.IsNot):
                return test.left.id, True
    if (
        isinstance(test, ast.UnaryOp)
        and isinstance(test.op, ast.Not)
        and isinstance(test.operand, ast.Name)
    ):
        return test.operand.id, False
    if isinstance(test, ast.Name):
        return test.id, True
    return None


def _walk_handler(stmts: list[ast.stmt]) -> Any:
    """Percorre o corpo do ramo sem descer em funções/classes aninhadas."""
    for st in stmts:
        yield st
        for child in ast.iter_child_nodes(st):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            yield from _walk_handler([child])  # type: ignore[list-item]


def _fallback_fabrica_sem_logar(corpo: list[ast.stmt]) -> int | None:
    """Linha do proxy, se o ramo de falha fabrica um valor SEM logar nem levantar."""
    linha_proxy: int | None = None
    for node in _walk_handler(corpo):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute) and f.attr in _LOG_ATTRS:
                return None  # registrou a degradação — comportamento correto
            if isinstance(f, ast.Name) and f.id == "print":
                return None
        if isinstance(node, ast.Raise):
            return None  # propagou — também correto
        if (
            isinstance(node, (ast.Assign, ast.AnnAssign, ast.Return))
            and linha_proxy is None
            and _valor_fabricado(node.value)
        ):
            linha_proxy = node.lineno
    return linha_proxy


def avaliar_ora006(entrada: Any, contexto: ExecutionContext) -> Any:
    del contexto
    try:
        dados = EntradaOra006.model_validate(entrada)
    except Exception as exc:
        raise EntradaInvalida(str(exc)) from exc

    if dados.conteudo is None:
        return SaidaOra006(achados=[]).model_dump()

    try:
        tree = ast.parse(dados.conteudo)
    except SyntaxError:
        return SaidaOra006(achados=[]).model_dump()

    linhas: list[int] = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        # nomes cujo valor veio de uma MEDIÇÃO (candidatos a falhar).
        # Passada ÚNICA sobre ast.walk(fn), acumulando `medidos` no caminho
        # — mesma ordem de visita do legado (um `if` visitado antes do
        # Assign correspondente não dispara, exatamente como lá).
        medidos: set[str] = set()
        for st in ast.walk(fn):
            if isinstance(st, ast.Assign) and _eh_medicao(st.value):
                for alvo in st.targets:
                    if isinstance(alvo, ast.Name):
                        medidos.add(alvo.id)
            elif isinstance(st, ast.If):
                guarda = _guarda_de_falha(st.test)
                if guarda is None or guarda[0] not in medidos:
                    continue
                ramo = st.orelse if guarda[1] else st.body
                proxy = _fallback_fabrica_sem_logar(ramo)
                if proxy is not None:
                    linhas.append(proxy)

    if not linhas:
        return SaidaOra006(achados=[]).model_dump()

    regra = dados.regra
    ls = ",".join(str(x) for x in sorted(set(linhas)))
    descricao = f"{dados.caminho}: medição None substituída por proxy sem log (linha(s) {ls})"
    achado = AchadoOra006(
        codigo=regra.codigo,
        agente=regra.agente,
        severidade=regra.severidade,
        categoria=regra.categoria,
        titulo=regra.titulo,
        descricao=descricao,
        causa=regra.causa,
        remediacao=regra.remediacao,
        arquivo=dados.caminho,
        chave="silent-measurement-proxy",
        fingerprint=_computar_fingerprint(dados.caminho, "silent-measurement-proxy"),
    )
    return SaidaOra006(achados=[achado]).model_dump()


def construir_implementacao() -> CapabilityImplementation:
    definicao = CapabilityDefinition(
        id=CapabilityId("ora006-proxy-de-medicao-silencioso"),
        name="ORA-006: medição None trocada por proxy sem log",
        version="1.0.0",
        input_schema=EntradaOra006.model_json_schema(),
        output_schema=SaidaOra006.model_json_schema(),
        deterministic=True,
        side_effects=SideEffects.NONE,
        idempotent=True,
    )

    conteudo_dispara = (
        "def build_outcome(entry, tgt):\n"
        "    mfe = measure_excursions(entry)\n"
        "    if mfe is None:\n"
        "        mfe = tgt - entry\n"
        "    return mfe\n"
    )
    conteudo_com_log = (
        "def build_outcome(entry, tgt):\n"
        "    mfe = measure_excursions(entry)\n"
        "    if mfe is None:\n"
        "        logger.warning('medicao falhou, usando proxy')\n"
        "        mfe = tgt - entry\n"
        "    return mfe\n"
    )
    entrada_sucesso = {"caminho": "src/x.py", "conteudo": conteudo_dispara, "regra": {}}
    entrada_com_log = {"caminho": "src/x.py", "conteudo": conteudo_com_log, "regra": {}}
    entrada_erro_sintaxe = {"caminho": "src/x.py", "conteudo": "def (:\n", "regra": {}}
    entrada_regra_invalida = {
        "caminho": "src/x.py",
        "conteudo": conteudo_dispara,
        "regra": {"severidade": 123},
    }

    return CapabilityImplementation(
        definition=definicao,
        handler=avaliar_ora006,
        acceptance_tests=[
            AcceptanceTest(
                name="medicao-none-com-proxy-sem-log-dispara",
                entrada=entrada_sucesso,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: len(saida["achados"]) == 1,
            ),
            AcceptanceTest(
                name="proxy-com-log-nao-dispara",
                entrada=entrada_com_log,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: saida["achados"] == [],
            ),
            AcceptanceTest(
                name="entrada-sem-campo-obrigatorio-e-rejeitada",
                entrada={"conteudo": "x"},
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
