"""Capability bespoke SRE-006 "endpoint crítico sem timeout de request no
servidor" (Vol.IV Cap.17).

Não generalizada em Skill — PRIORIDADE de arquivo: se `gunicorn.conf.py`
existe na raiz, SÓ ele é checado (achado 0 ou 1) e `scripts/` NUNCA é
escaneado, mesmo que `gunicorn.conf.py` passe na checagem. Só na
AUSÊNCIA de `gunicorn.conf.py` o fallback para `scripts/*.sh`+`*.py`
entra em cena, com branch gunicorn-vs-uvicorn por arquivo e mensagens
diferentes — múltiplos achados possíveis (1 por script que lança
gunicorn/uvicorn sem timeout)."""

from __future__ import annotations

import json
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

_GUNICORN_TIMEOUT = re.compile(r"timeout")
_UVICORN_TIMEOUT = re.compile(r"--timeout-keep-alive")
_LAUNCH_RE = re.compile(
    r"(subprocess|Popen|os\.system|os\.exec|check_call|check_output|run)\b[^)]*"
    r"(uvicorn|gunicorn)|[\"']uvicorn\s+\w|[\"']gunicorn\s+\w"
    r"|^\s*(?:exec\s+)?(?:uvicorn|gunicorn)\s+\w",
    re.I | re.M,
)


class RegraSre006Spec(BaseModel):
    codigo: str
    agente: str
    severidade: str
    categoria: str
    titulo: str
    causa: str
    remediacao: str


class EntradaSre006(BaseModel):
    tipo: Literal["sre006"] = "sre006"
    caminho: str
    conteudo: str | None = None
    regra: RegraSre006Spec


class AchadoSre006(BaseModel):
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


class SaidaSre006(BaseModel):
    achados: list[AchadoSre006] = Field(default_factory=list)


class EntradaInvalida(Exception):
    """Levantada quando `entrada` não satisfaz `EntradaSre006` — vira
    SCHEMA_REJECTION no Execution Engine (Vol.III Cap.12)."""


def _computar_fingerprint(agente: str, categoria: str, caminho: str, codigo: str) -> str:
    import hashlib

    normalizado = caminho.replace("\\", "/")
    bruto = f"{agente}|{categoria}|{normalizado}|{codigo}|"
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()


def _achado(regra: RegraSre006Spec, caminho: str, descricao: str) -> AchadoSre006:
    fingerprint = _computar_fingerprint(regra.agente, regra.categoria, caminho, regra.codigo)
    return AchadoSre006(
        codigo=regra.codigo,
        agente=regra.agente,
        severidade=regra.severidade,
        categoria=regra.categoria,
        titulo=regra.titulo,
        descricao=descricao,
        causa=regra.causa,
        remediacao=regra.remediacao,
        arquivo=caminho,
        fingerprint=fingerprint,
    )


def avaliar_sre006(entrada: Any, contexto: ExecutionContext) -> Any:
    del contexto
    try:
        dados = EntradaSre006.model_validate(entrada)
    except Exception as exc:
        raise EntradaInvalida(str(exc)) from exc

    if dados.conteudo is None:
        return SaidaSre006(achados=[]).model_dump()

    payload = json.loads(dados.conteudo)
    regra = dados.regra

    gunicorn_conf_texto = payload.get("gunicorn_conf_texto")
    if gunicorn_conf_texto is not None:
        if _GUNICORN_TIMEOUT.search(gunicorn_conf_texto):
            return SaidaSre006(achados=[]).model_dump()
        achado = _achado(regra, "gunicorn.conf.py", "gunicorn.conf.py sem configuração de timeout.")
        return SaidaSre006(achados=[achado]).model_dump()

    scripts: list[tuple[str, str]] = payload.get("scripts", [])
    achados: list[AchadoSre006] = []
    for caminho_script, texto in scripts:
        if not _LAUNCH_RE.search(texto):
            continue
        if "gunicorn" in texto and not _GUNICORN_TIMEOUT.search(texto):
            achados.append(
                _achado(regra, caminho_script, f"{caminho_script}: gunicorn sem --timeout.")
            )
        elif "uvicorn" in texto and not _UVICORN_TIMEOUT.search(texto):
            achados.append(
                _achado(
                    regra, caminho_script, f"{caminho_script}: uvicorn sem --timeout-keep-alive."
                )
            )

    return SaidaSre006(achados=achados).model_dump()


def construir_implementacao() -> CapabilityImplementation:
    definicao = CapabilityDefinition(
        id=CapabilityId("sre006-timeout-ausente"),
        name="SRE-006 endpoint critico sem timeout de request",
        version="1.0.0",
        input_schema=EntradaSre006.model_json_schema(),
        output_schema=SaidaSre006.model_json_schema(),
        deterministic=True,
        side_effects=SideEffects.NONE,
        idempotent=True,
    )

    _regra_teste = {
        "codigo": "SRE-006",
        "agente": "sre",
        "severidade": "high",
        "categoria": "resiliencia",
        "titulo": "t",
        "causa": "c",
        "remediacao": "r",
    }
    entrada_sucesso = {
        "caminho": "gunicorn.conf.py",
        "conteudo": json.dumps({"gunicorn_conf_texto": "workers = 4\n"}),
        "regra": _regra_teste,
    }
    entrada_ok = {
        "caminho": "gunicorn.conf.py",
        "conteudo": json.dumps({"gunicorn_conf_texto": "timeout = 30\n"}),
        "regra": _regra_teste,
    }

    return CapabilityImplementation(
        definition=definicao,
        handler=avaliar_sre006,
        acceptance_tests=[
            AcceptanceTest(
                name="gunicorn-conf-sem-timeout-dispara",
                entrada=entrada_sucesso,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: len(saida["achados"]) == 1,
            ),
            AcceptanceTest(
                name="gunicorn-conf-com-timeout-nao-dispara",
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
                    "caminho": "gunicorn.conf.py",
                    "conteudo": "x",
                    "regra": {"severidade": 123},
                },
                resultado_esperado=ResultadoEsperado.TIMEOUT,
            ),
        ],
    )
