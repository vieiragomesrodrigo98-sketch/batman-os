"""Capability bespoke REV-006 "nome de variável com 1–2 caracteres fora
de loops curtos e lambdas matemáticos" (Vol.IV Cap.17).

Não generalizada em `janela_contexto_regex`/`metrica_com_limiar` — a
condição de disparo depende de um frozenset de ~90 abreviações canônicas
aceitas (Python/FastAPI/async/domínio financeiro), grande demais para
expressar como uma alternação regex sem risco de erro de transcrição;
mais seguro reproduzir o frozenset Python literal do legado."""

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

_EXCEPTIONS: frozenset[str] = frozenset(
    {
        # Todas as letras minúsculas de 1 char (ruído demais pra sinalizar)
        "a",
        "b",
        "c",
        "d",
        "e",
        "f",
        "g",
        "h",
        "i",
        "j",
        "k",
        "l",
        "m",
        "n",
        "o",
        "p",
        "q",
        "r",
        "s",
        "t",
        "u",
        "v",
        "w",
        "x",
        "y",
        "z",
        # 2 chars — abreviações canônicas Python/FastAPI/async
        "db",
        "fn",
        "tp",
        "ok",
        "to",
        "id",
        "by",
        "at",
        "ts",
        "dt",
        "tz",
        "pk",
        "fk",
        "ex",
        "io",
        "op",
        "st",
        "cb",
        "df",
        "ax",
        "rv",
        "ct",
        "ch",
        "sq",
        "re",
        "os",
        "wd",
        "nl",
        "co",
        "rc",
        "fp",
        "dp",
        "wr",
        "cf",
        "wf",
        "nr",
        "kw",
        "pr",
        "cr",
        "tr",
        "sb",
        "lc",
        "rp",
        "mp",
        "sp",
        "cp",
        "ep",
        "tk",
        "ms",
        "ws",
        "rs",
        "gc",
        "go",
        "mo",
        "lp",
        "rb",
        "vl",
        "bo",
        "ro",
        "ho",
        "br",
        "sk",
        "nk",
        "hr",
        "lr",
        "sr",
        # Rede / auth
        "ip",
        "pw",
        # Abreviações financeiras/domínio
        "tl",
        "ev",
        "bc",
        "bs",
        "ls",
        "up",
        "dn",
        "pf",
        "et",
        "eq",
        "dd",
        "ge",
        "le",
        "ps",
        "bm",
        "pe",
        "pb",
        "pl",
        "rf",
        "bk",
        "ir",
        "ic",
        "rr",
    }
)

_PATTERN = re.compile(r"^\s*([a-zA-Z]{1,2})\s*=\s*[^=]")


class RegraRev006Spec(BaseModel):
    codigo: str
    agente: str
    severidade: str
    categoria: str
    titulo: str
    causa: str
    remediacao: str


class EntradaRev006(BaseModel):
    tipo: Literal["rev006"] = "rev006"
    caminho: str
    conteudo: str | None = None
    regra: RegraRev006Spec


class AchadoRev006(BaseModel):
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


class SaidaRev006(BaseModel):
    achados: list[AchadoRev006] = Field(default_factory=list)


class EntradaInvalida(Exception):
    """Levantada quando `entrada` não satisfaz `EntradaRev006` — vira
    SCHEMA_REJECTION no Execution Engine (Vol.III Cap.12)."""


def _computar_fingerprint(agente: str, categoria: str, caminho: str, codigo: str) -> str:
    import hashlib

    normalizado = caminho.replace("\\", "/")
    bruto = f"{agente}|{categoria}|{normalizado}|{codigo}|"
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()


def _fmt_lines(lines: list[int]) -> str:
    return ",".join(str(x) for x in sorted(set(lines)))


def avaliar_rev006(entrada: Any, contexto: ExecutionContext) -> Any:
    del contexto
    try:
        dados = EntradaRev006.model_validate(entrada)
    except Exception as exc:
        raise EntradaInvalida(str(exc)) from exc

    rel = dados.caminho.replace("\\", "/")
    if "test" in rel:
        return SaidaRev006(achados=[]).model_dump()

    if dados.conteudo is None:
        return SaidaRev006(achados=[]).model_dump()

    lines_with_hits: list[int] = []
    for lineno, line in enumerate(dados.conteudo.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("for "):
            continue
        m = _PATTERN.match(line)
        if m:
            var = m.group(1).lower()
            if var not in _EXCEPTIONS:
                lines_with_hits.append(lineno)

    if not lines_with_hits:
        return SaidaRev006(achados=[]).model_dump()

    regra = dados.regra
    fingerprint = _computar_fingerprint(regra.agente, regra.categoria, dados.caminho, regra.codigo)
    achado = AchadoRev006(
        codigo=regra.codigo,
        agente=regra.agente,
        severidade=regra.severidade,
        categoria=regra.categoria,
        titulo=regra.titulo,
        descricao=(
            f"{dados.caminho}: variáveis com nome curto (linhas {_fmt_lines(lines_with_hits)})."
        ),
        causa=regra.causa,
        remediacao=regra.remediacao,
        arquivo=dados.caminho,
        fingerprint=fingerprint,
    )
    return SaidaRev006(achados=[achado]).model_dump()


def construir_implementacao() -> CapabilityImplementation:
    definicao = CapabilityDefinition(
        id=CapabilityId("rev006-variavel-nome-curto"),
        name="REV-006 nome de variavel com 1-2 caracteres",
        version="1.0.0",
        input_schema=EntradaRev006.model_json_schema(),
        output_schema=SaidaRev006.model_json_schema(),
        deterministic=True,
        side_effects=SideEffects.NONE,
        idempotent=True,
    )

    _regra_teste = {
        "codigo": "REV-006",
        "agente": "code-reviewer",
        "severidade": "low",
        "categoria": "manutenibilidade",
        "titulo": "t",
        "causa": "c",
        "remediacao": "r",
    }
    entrada_sucesso = {
        "caminho": "api/x.py",
        "conteudo": "zz = calcular()\n",
        "regra": _regra_teste,
    }
    entrada_ok = {
        "caminho": "api/x.py",
        "conteudo": "db = conectar()\n",
        "regra": _regra_teste,
    }

    return CapabilityImplementation(
        definition=definicao,
        handler=avaliar_rev006,
        acceptance_tests=[
            AcceptanceTest(
                name="variavel-curta-fora-da-lista-de-excecoes-dispara",
                entrada=entrada_sucesso,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: len(saida["achados"]) == 1,
            ),
            AcceptanceTest(
                name="variavel-curta-na-lista-de-excecoes-nao-dispara",
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
                    "caminho": "api/x.py",
                    "conteudo": "x",
                    "regra": {"severidade": 123},
                },
                resultado_esperado=ResultadoEsperado.TIMEOUT,
            ),
        ],
    )
