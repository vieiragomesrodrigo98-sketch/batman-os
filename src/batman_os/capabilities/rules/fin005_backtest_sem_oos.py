"""Capability bespoke FIN-005 "backtest sem período de validação
out-of-sample separado" (Vol.IV Cap.17).

Não generalizada em `regex_sobre_conteudo` — o gate de entrada é um OR
entre uma condição de NOME DE ARQUIVO (substring "backtest", case-
insensitive) e uma condição de CONTEÚDO (`def/class` com "backtest" no
nome), algo que a Skill não suporta (`pattern_nome_arquivo_incluir` é um
AND independente, não uma alternativa a um pattern de conteúdo). As duas
condições de AUSÊNCIA (out-of-sample / split train-test) já se combinam
numa única alternação regex, sem precisar de campo novo."""

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

_OOS_OU_SPLIT_RE = re.compile(
    r"walk_forward|out_of_sample|walk-forward|\btrain\b.*\btest\b|\btest\b.*\btrain\b", re.I
)
_BACKTEST_CODE_RE = re.compile(r"def\s+\w*backtest|class\s+\w*[Bb]acktest", re.I)


class RegraFin005Spec(BaseModel):
    codigo: str
    agente: str
    severidade: str
    categoria: str
    titulo: str
    causa: str
    remediacao: str


class EntradaFin005(BaseModel):
    tipo: Literal["fin005"] = "fin005"
    caminho: str
    conteudo: str | None = None
    regra: RegraFin005Spec


class AchadoFin005(BaseModel):
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


class SaidaFin005(BaseModel):
    achados: list[AchadoFin005] = Field(default_factory=list)


class EntradaInvalida(Exception):
    """Levantada quando `entrada` não satisfaz `EntradaFin005` — vira
    SCHEMA_REJECTION no Execution Engine (Vol.III Cap.12)."""


def _computar_fingerprint(agente: str, categoria: str, caminho: str, codigo: str) -> str:
    import hashlib

    normalizado = caminho.replace("\\", "/")
    bruto = f"{agente}|{categoria}|{normalizado}|{codigo}|"
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()


def avaliar_fin005(entrada: Any, contexto: ExecutionContext) -> Any:
    del contexto
    try:
        dados = EntradaFin005.model_validate(entrada)
    except Exception as exc:
        raise EntradaInvalida(str(exc)) from exc

    if dados.conteudo is None:
        return SaidaFin005(achados=[]).model_dump()

    nome_arquivo = dados.caminho.replace("\\", "/").rsplit("/", 1)[-1]
    in_name = "backtest" in nome_arquivo.lower()
    in_code = _BACKTEST_CODE_RE.search(dados.conteudo) is not None
    if not (in_name or in_code):
        return SaidaFin005(achados=[]).model_dump()

    if _OOS_OU_SPLIT_RE.search(dados.conteudo):
        return SaidaFin005(achados=[]).model_dump()

    regra = dados.regra
    fingerprint = _computar_fingerprint(regra.agente, regra.categoria, dados.caminho, regra.codigo)
    achado = AchadoFin005(
        codigo=regra.codigo,
        agente=regra.agente,
        severidade=regra.severidade,
        categoria=regra.categoria,
        titulo=regra.titulo,
        descricao=f"{dados.caminho}: backtest sem validação out-of-sample.",
        causa=regra.causa,
        remediacao=regra.remediacao,
        arquivo=dados.caminho,
        fingerprint=fingerprint,
    )
    return SaidaFin005(achados=[achado]).model_dump()


def construir_implementacao() -> CapabilityImplementation:
    definicao = CapabilityDefinition(
        id=CapabilityId("fin005-backtest-sem-oos"),
        name="FIN-005 backtest sem out-of-sample",
        version="1.0.0",
        input_schema=EntradaFin005.model_json_schema(),
        output_schema=SaidaFin005.model_json_schema(),
        deterministic=True,
        side_effects=SideEffects.NONE,
        idempotent=True,
    )

    _regra_teste = {
        "codigo": "FIN-005",
        "agente": "financial-analyst",
        "severidade": "high",
        "categoria": "validacao",
        "titulo": "t",
        "causa": "c",
        "remediacao": "r",
    }
    entrada_sucesso = {
        "caminho": "src/backtest_engine.py",
        "conteudo": "def run():\n    pass\n",
        "regra": _regra_teste,
    }
    entrada_ok = {
        "caminho": "src/backtest_engine.py",
        "conteudo": "def run():\n    walk_forward()\n",
        "regra": _regra_teste,
    }

    return CapabilityImplementation(
        definition=definicao,
        handler=avaliar_fin005,
        acceptance_tests=[
            AcceptanceTest(
                name="backtest-por-nome-sem-oos-dispara",
                entrada=entrada_sucesso,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: len(saida["achados"]) == 1,
            ),
            AcceptanceTest(
                name="backtest-com-walk-forward-nao-dispara",
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
                    "caminho": "src/backtest_engine.py",
                    "conteudo": "x",
                    "regra": {"severidade": 123},
                },
                resultado_esperado=ResultadoEsperado.TIMEOUT,
            ),
        ],
    )
