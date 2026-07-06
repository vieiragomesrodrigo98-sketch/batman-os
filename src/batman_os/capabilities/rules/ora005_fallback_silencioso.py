"""Capability bespoke — ORA-005 (Vol.IV Cap.17) — Milestone 3, Skill 6.

Replica `Batman/scan/rules/oracle.py::SilentFallbackReturn`: acha `except`
amplo (`Exception`/`BaseException`/bare) que devolve um `return <valor>` sem
logar nem re-levantar — o mecanismo exato do incidente C1 (auditoria
jul/2026): auto-calibragem rodou meses devolvendo pesos default porque um
`NameError` era engolido por `except Exception: return _defaults`.

Diferente de DE-003/ORA-004, esta análise é POR ARQUIVO (sem agregação
entre arquivos) — usa a mesma descoberta `"arvore"` já existente (1 Missão
por arquivo), só o handler é bespoke (percorre `ast.Try`/`ExceptHandler`,
padrão que não se repete em nenhuma Skill genérica migrada)."""

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
CODIGO = "ORA-005"

_LOG_ATTRS = {"debug", "info", "warning", "warn", "error", "exception", "critical", "log"}


class RegraOra005Spec(BaseModel):
    codigo: str = CODIGO
    agente: str = AGENTE
    severidade: str = "high"
    categoria: str = CATEGORIA
    titulo: str = "except amplo devolve fallback sem log — feature pode morrer em silêncio"
    causa: str = (
        "O mecanismo exato do C1 (auditoria jul/2026): a auto-calibragem rodou meses "
        "devolvendo pesos default porque um NameError era engolido por "
        "'except Exception: return _defaults'. Um except amplo que devolve fallback "
        "sem logar nem re-levantar transforma qualquer bug futuro em feature "
        "silenciosamente morta — o pior modo de falha possível."
    )
    remediacao: str = (
        "Adicione log no handler (logger.warning/exception com o erro) ou estreite a "
        "exceção capturada. O fallback pode continuar existindo — o que não pode é ser "
        "invisível. DoD: todo except amplo com return de fallback loga o erro capturado."
    )


class EntradaOra005(BaseModel):
    """`tipo` é o mesmo discriminador estrutural usado em todas as Entradas
    desta migração (ver docstring de `EntradaAst.tipo`) — sem ele, o schema
    de 3 chaves (`caminho`/`conteudo`/`regra`) seria um subconjunto válido
    de outras Capabilities e `CapabilityRegistry.find_candidates` as
    confundiria."""

    tipo: Literal["ora005"] = "ora005"
    caminho: str
    conteudo: str | None = None
    regra: RegraOra005Spec = Field(default_factory=RegraOra005Spec)


class AchadoOra005(BaseModel):
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


class SaidaOra005(BaseModel):
    achados: list[AchadoOra005] = Field(default_factory=list)


class EntradaInvalida(Exception):
    """Levantada quando `entrada` não satisfaz `EntradaOra005` — vira
    SCHEMA_REJECTION no Execution Engine (Vol.III Cap.12)."""


def _computar_fingerprint(caminho: str, chave: str) -> str:
    normalizado = caminho.replace("\\", "/")
    bruto = f"{AGENTE}|{CATEGORIA}|{normalizado}|{CODIGO}|{chave}"
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()


def _is_broad_handler(handler: ast.ExceptHandler) -> bool:
    t = handler.type
    if t is None:
        return True
    if isinstance(t, ast.Name):
        return t.id in ("Exception", "BaseException")
    if isinstance(t, ast.Tuple):
        return any(
            isinstance(e, ast.Name) and e.id in ("Exception", "BaseException") for e in t.elts
        )
    return False


def _walk_handler(stmts: list[ast.stmt]) -> Any:
    for st in stmts:
        yield st
        for child in ast.iter_child_nodes(st):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            yield from _walk_handler([child])  # type: ignore[list-item]


def _handler_logs_or_raises(handler: ast.ExceptHandler) -> bool:
    for node in _walk_handler(handler.body):
        if isinstance(node, ast.Raise):
            return True
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute) and f.attr in _LOG_ATTRS:
                return True
            if isinstance(f, ast.Name) and f.id == "print":
                return True
    return False


def _handler_returns_value(handler: ast.ExceptHandler) -> int | None:
    for node in _walk_handler(handler.body):
        if isinstance(node, ast.Return) and node.value is not None:
            return node.lineno
    return None


def avaliar_ora005(entrada: Any, contexto: ExecutionContext) -> Any:
    del contexto
    try:
        dados = EntradaOra005.model_validate(entrada)
    except Exception as exc:
        raise EntradaInvalida(str(exc)) from exc

    if dados.conteudo is None:
        return SaidaOra005(achados=[]).model_dump()

    try:
        tree = ast.parse(dados.conteudo)
    except SyntaxError:
        return SaidaOra005(achados=[]).model_dump()

    linhas: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        for handler in node.handlers:
            if not _is_broad_handler(handler):
                continue
            if _handler_logs_or_raises(handler):
                continue
            ret_line = _handler_returns_value(handler)
            if ret_line is not None:
                linhas.append(handler.lineno)

    if not linhas:
        return SaidaOra005(achados=[]).model_dump()

    regra = dados.regra
    ls = ",".join(str(x) for x in sorted(set(linhas)))
    descricao = f"{dados.caminho}: except amplo com return de fallback sem log (linha(s) {ls})"
    achado = AchadoOra005(
        codigo=regra.codigo,
        agente=regra.agente,
        severidade=regra.severidade,
        categoria=regra.categoria,
        titulo=regra.titulo,
        descricao=descricao,
        causa=regra.causa,
        remediacao=regra.remediacao,
        arquivo=dados.caminho,
        chave="silent-fallback",
        fingerprint=_computar_fingerprint(dados.caminho, "silent-fallback"),
    )
    return SaidaOra005(achados=[achado]).model_dump()


def construir_implementacao() -> CapabilityImplementation:
    definicao = CapabilityDefinition(
        id=CapabilityId("ora005-fallback-silencioso"),
        name="ORA-005: except amplo com fallback silencioso",
        version="1.0.0",
        input_schema=EntradaOra005.model_json_schema(),
        output_schema=SaidaOra005.model_json_schema(),
        deterministic=True,
        side_effects=SideEffects.NONE,
        idempotent=True,
    )

    conteudo_dispara = (
        "def f():\n"
        "    try:\n"
        "        return calcular()\n"
        "    except Exception:\n"
        "        return _defaults\n"
    )
    conteudo_com_log = (
        "def f():\n"
        "    try:\n"
        "        return calcular()\n"
        "    except Exception as e:\n"
        "        logger.warning(e)\n"
        "        return _defaults\n"
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
        handler=avaliar_ora005,
        acceptance_tests=[
            AcceptanceTest(
                name="except-amplo-com-fallback-sem-log-dispara",
                entrada=entrada_sucesso,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: len(saida["achados"]) == 1,
            ),
            AcceptanceTest(
                name="except-com-log-nao-dispara",
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
