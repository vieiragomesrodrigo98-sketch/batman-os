"""Capability bespoke PERF-004 "arquivo carregado completamente em
memória sem streaming" (Vol.IV Cap.17).

Não generalizada em Skill — DOIS padrões com `continue` MUTUAMENTE
EXCLUSIVO por arquivo (`file.read()` OU `pd.read_csv` sem `chunksize`):
2 specs independentes de `regex_sobre_conteudo` produziriam DOIS achados
num arquivo que tem AMBOS os padrões, mas o legado só produz 1 (o
primeiro check, se disparar, suprime o segundo via `continue`)."""

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

_FULL_READ_RE = re.compile(r"file\.read\s*\(\s*\)", re.I)
_CSV_CHUNK_RE = re.compile(r"pd\.read_csv\s*\(", re.I)
_CHUNKSIZE_RE = re.compile(r"chunksize\s*=", re.I)


class RegraPerf004Spec(BaseModel):
    codigo: str
    agente: str
    severidade: str
    categoria: str
    titulo: str
    causa: str
    remediacao: str


class EntradaPerf004(BaseModel):
    tipo: Literal["perf004"] = "perf004"
    caminho: str
    conteudo: str | None = None
    regra: RegraPerf004Spec


class AchadoPerf004(BaseModel):
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


class SaidaPerf004(BaseModel):
    achados: list[AchadoPerf004] = Field(default_factory=list)


class EntradaInvalida(Exception):
    """Levantada quando `entrada` não satisfaz `EntradaPerf004` — vira
    SCHEMA_REJECTION no Execution Engine (Vol.III Cap.12)."""


def _computar_fingerprint(agente: str, categoria: str, caminho: str, codigo: str) -> str:
    import hashlib

    normalizado = caminho.replace("\\", "/")
    bruto = f"{agente}|{categoria}|{normalizado}|{codigo}|"
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()


def _fmt_lines(lines: list[int]) -> str:
    return ",".join(str(x) for x in sorted(set(lines)))


def _linhas_que_casam(text: str, pattern: re.Pattern[str]) -> list[int]:
    return [i for i, line in enumerate(text.splitlines(), 1) if pattern.search(line)]


def avaliar_perf004(entrada: Any, contexto: ExecutionContext) -> Any:
    del contexto
    try:
        dados = EntradaPerf004.model_validate(entrada)
    except Exception as exc:
        raise EntradaInvalida(str(exc)) from exc

    if dados.conteudo is None:
        return SaidaPerf004(achados=[]).model_dump()

    text = dados.conteudo
    regra = dados.regra

    lines = _linhas_que_casam(text, _FULL_READ_RE)
    if lines:
        descricao = (
            f"{dados.caminho}: arquivo lido completamente em memória (linhas {_fmt_lines(lines)})."
        )
    elif _CSV_CHUNK_RE.search(text) and not _CHUNKSIZE_RE.search(text):
        lines = _linhas_que_casam(text, _CSV_CHUNK_RE)
        if not lines:
            return SaidaPerf004(achados=[]).model_dump()
        descricao = (
            f"{dados.caminho}: arquivo lido completamente em memória via pd.read_csv "
            f"(linhas {_fmt_lines(lines)})."
        )
    else:
        return SaidaPerf004(achados=[]).model_dump()

    fingerprint = _computar_fingerprint(regra.agente, regra.categoria, dados.caminho, regra.codigo)
    achado = AchadoPerf004(
        codigo=regra.codigo,
        agente=regra.agente,
        severidade=regra.severidade,
        categoria=regra.categoria,
        titulo=regra.titulo,
        descricao=descricao,
        causa=regra.causa,
        remediacao=regra.remediacao,
        arquivo=dados.caminho,
        fingerprint=fingerprint,
    )
    return SaidaPerf004(achados=[achado]).model_dump()


def construir_implementacao() -> CapabilityImplementation:
    definicao = CapabilityDefinition(
        id=CapabilityId("perf004-arquivo-sem-streaming"),
        name="PERF-004 arquivo carregado completamente em memoria",
        version="1.0.0",
        input_schema=EntradaPerf004.model_json_schema(),
        output_schema=SaidaPerf004.model_json_schema(),
        deterministic=True,
        side_effects=SideEffects.NONE,
        idempotent=True,
    )

    _regra_teste = {
        "codigo": "PERF-004",
        "agente": "performance-engineer",
        "severidade": "medium",
        "categoria": "memoria",
        "titulo": "t",
        "causa": "c",
        "remediacao": "r",
    }
    entrada_sucesso = {
        "caminho": "api/routers/upload.py",
        "conteudo": "conteudo = file.read()\n",
        "regra": _regra_teste,
    }
    entrada_ok = {
        "caminho": "api/routers/upload.py",
        "conteudo": "df = pd.read_csv(f, chunksize=1000)\n",
        "regra": _regra_teste,
    }

    return CapabilityImplementation(
        definition=definicao,
        handler=avaliar_perf004,
        acceptance_tests=[
            AcceptanceTest(
                name="file-read-completo-dispara",
                entrada=entrada_sucesso,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: len(saida["achados"]) == 1,
            ),
            AcceptanceTest(
                name="read-csv-com-chunksize-nao-dispara",
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
