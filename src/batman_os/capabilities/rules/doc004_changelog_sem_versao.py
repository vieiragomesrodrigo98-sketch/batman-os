"""Capability bespoke DOC-004 "CHANGELOG.md sem entrada correspondente à
versão atual de pyproject.toml" (Vol.IV Cap.17).

Não generalizada em Skill — extrai um VALOR (a versão) de um arquivo via
regex e verifica se essa STRING aparece em OUTRO arquivo; não é presença/
ausência de padrão fixo, é comparação de valor computado entre 2
fontes."""

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

_VERSION_RE = re.compile(r"version\s*=\s*[\"']([^\"']+)[\"']")


class RegraDoc004Spec(BaseModel):
    codigo: str
    agente: str
    severidade: str
    categoria: str
    titulo: str
    causa: str
    remediacao: str


class EntradaDoc004(BaseModel):
    tipo: Literal["doc004"] = "doc004"
    caminho: str
    conteudo: str | None = None
    regra: RegraDoc004Spec


class AchadoDoc004(BaseModel):
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


class SaidaDoc004(BaseModel):
    achados: list[AchadoDoc004] = Field(default_factory=list)


class EntradaInvalida(Exception):
    """Levantada quando `entrada` não satisfaz `EntradaDoc004` — vira
    SCHEMA_REJECTION no Execution Engine (Vol.III Cap.12)."""


def _computar_fingerprint(agente: str, categoria: str, caminho: str, codigo: str) -> str:
    import hashlib

    normalizado = caminho.replace("\\", "/")
    bruto = f"{agente}|{categoria}|{normalizado}|{codigo}|"
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()


def avaliar_doc004(entrada: Any, contexto: ExecutionContext) -> Any:
    del contexto
    try:
        dados = EntradaDoc004.model_validate(entrada)
    except Exception as exc:
        raise EntradaInvalida(str(exc)) from exc

    if dados.conteudo is None:
        return SaidaDoc004(achados=[]).model_dump()

    payload = json.loads(dados.conteudo)
    pyproject_texto: str | None = payload.get("pyproject_texto")
    changelog_texto: str | None = payload.get("changelog_texto")
    if pyproject_texto is None or changelog_texto is None:
        return SaidaDoc004(achados=[]).model_dump()

    m = _VERSION_RE.search(pyproject_texto)
    if not m:
        return SaidaDoc004(achados=[]).model_dump()

    version = m.group(1)
    if version in changelog_texto:
        return SaidaDoc004(achados=[]).model_dump()

    regra = dados.regra
    fingerprint = _computar_fingerprint(regra.agente, regra.categoria, dados.caminho, regra.codigo)
    achado = AchadoDoc004(
        codigo=regra.codigo,
        agente=regra.agente,
        severidade=regra.severidade,
        categoria=regra.categoria,
        titulo=regra.titulo,
        descricao=f"CHANGELOG.md não contém a versão atual {version} de pyproject.toml.",
        causa=regra.causa,
        remediacao=regra.remediacao,
        arquivo=dados.caminho,
        fingerprint=fingerprint,
    )
    return SaidaDoc004(achados=[achado]).model_dump()


def construir_implementacao() -> CapabilityImplementation:
    definicao = CapabilityDefinition(
        id=CapabilityId("doc004-changelog-sem-versao"),
        name="DOC-004 CHANGELOG sem versao correspondente",
        version="1.0.0",
        input_schema=EntradaDoc004.model_json_schema(),
        output_schema=SaidaDoc004.model_json_schema(),
        deterministic=True,
        side_effects=SideEffects.NONE,
        idempotent=True,
    )

    _regra_teste = {
        "codigo": "DOC-004",
        "agente": "technical-writer",
        "severidade": "low",
        "categoria": "documentacao",
        "titulo": "t",
        "causa": "c",
        "remediacao": "r",
    }
    entrada_sucesso = {
        "caminho": "CHANGELOG.md",
        "conteudo": json.dumps(
            {
                "pyproject_texto": '[project]\nversion = "1.2.3"\n',
                "changelog_texto": "## 1.0.0\n- inicial\n",
            }
        ),
        "regra": _regra_teste,
    }
    entrada_ok = {
        "caminho": "CHANGELOG.md",
        "conteudo": json.dumps(
            {
                "pyproject_texto": '[project]\nversion = "1.2.3"\n',
                "changelog_texto": "## 1.2.3\n- release atual\n",
            }
        ),
        "regra": _regra_teste,
    }

    return CapabilityImplementation(
        definition=definicao,
        handler=avaliar_doc004,
        acceptance_tests=[
            AcceptanceTest(
                name="changelog-sem-versao-atual-dispara",
                entrada=entrada_sucesso,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: len(saida["achados"]) == 1,
            ),
            AcceptanceTest(
                name="changelog-com-versao-atual-nao-dispara",
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
                    "caminho": "CHANGELOG.md",
                    "conteudo": "x",
                    "regra": {"severidade": 123},
                },
                resultado_esperado=ResultadoEsperado.TIMEOUT,
            ),
        ],
    )
