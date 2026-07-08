"""Capability bespoke ARCH-003 "página Streamlit órfã" (Vol.IV Cap.17).

Não generalizada numa Skill — cross-reference ENTRE arquivos com
cardinalidade invertida: N páginas candidatas (`pages/*.py`) vs. 1
arquivo agregador (`dashboard/app.py`). Diferente de `regex_agregado_
multi_arquivo` (que produz NO MÁXIMO 1 achado para o LOTE inteiro): aqui
cada página órfã produz seu PRÓPRIO achado, com seu PRÓPRIO `caminho` —
logo fingerprints DIFERENTES por página (replica o legado, que faz
`yield` por página órfã com `path=rel` distinto por achado).

A descoberta (`descoberta_arquivos.py::_resultado_arch003`) lê o
agregador UMA VEZ e o repete como `conteudo` de CADA Missão de página —
o handler só verifica se o próprio nome (stem) do arquivo aparece nesse
texto compartilhado."""

from __future__ import annotations

from pathlib import PurePosixPath
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


class RegraArch003Spec(BaseModel):
    codigo: str
    agente: str
    severidade: str
    categoria: str
    titulo: str
    causa: str
    remediacao: str
    caminho_agregador: str


class EntradaArch003(BaseModel):
    tipo: Literal["arch003"] = "arch003"
    caminho: str
    conteudo: str | None = None
    regra: RegraArch003Spec


class AchadoArch003(BaseModel):
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


class SaidaArch003(BaseModel):
    achados: list[AchadoArch003] = Field(default_factory=list)


class EntradaInvalida(Exception):
    """Levantada quando `entrada` não satisfaz `EntradaArch003` — vira
    SCHEMA_REJECTION no Execution Engine (Vol.III Cap.12)."""


def _computar_fingerprint(agente: str, categoria: str, caminho: str, codigo: str) -> str:
    import hashlib

    normalizado = caminho.replace("\\", "/")
    bruto = f"{agente}|{categoria}|{normalizado}|{codigo}|"
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()


def avaliar_arch003(entrada: Any, contexto: ExecutionContext) -> Any:
    del contexto
    try:
        dados = EntradaArch003.model_validate(entrada)
    except Exception as exc:
        raise EntradaInvalida(str(exc)) from exc

    if dados.conteudo is None:
        # Agregador (dashboard/app.py) nao existe -> legado retorna sem
        # achado nenhum (nao ha onde a pagina poderia estar registrada).
        return SaidaArch003(achados=[]).model_dump()

    stem = PurePosixPath(dados.caminho.replace("\\", "/")).stem
    if stem in dados.conteudo:
        return SaidaArch003(achados=[]).model_dump()

    regra = dados.regra
    fingerprint = _computar_fingerprint(regra.agente, regra.categoria, dados.caminho, regra.codigo)
    achado = AchadoArch003(
        codigo=regra.codigo,
        agente=regra.agente,
        severidade=regra.severidade,
        categoria=regra.categoria,
        titulo=regra.titulo,
        descricao=f"{dados.caminho} não é referenciada em {regra.caminho_agregador}.",
        causa=regra.causa,
        remediacao=regra.remediacao,
        arquivo=dados.caminho,
        fingerprint=fingerprint,
    )
    return SaidaArch003(achados=[achado]).model_dump()


def construir_implementacao() -> CapabilityImplementation:
    definicao = CapabilityDefinition(
        id=CapabilityId("arch003-pagina-orfa"),
        name="ARCH-003 pagina Streamlit orfa",
        version="1.0.0",
        input_schema=EntradaArch003.model_json_schema(),
        output_schema=SaidaArch003.model_json_schema(),
        deterministic=True,
        side_effects=SideEffects.NONE,
        idempotent=True,
    )

    _regra_teste = {
        "codigo": "ARCH-003",
        "agente": "software-architect",
        "severidade": "medium",
        "categoria": "navigation",
        "titulo": "t",
        "causa": "c",
        "remediacao": "r",
        "caminho_agregador": "dashboard/app.py",
    }
    entrada_sucesso = {
        "caminho": "pages/orfa.py",
        "conteudo": "import outra_pagina\n",
        "regra": _regra_teste,
    }
    entrada_ok = {
        "caminho": "pages/registrada.py",
        "conteudo": "import registrada\n",
        "regra": _regra_teste,
    }

    return CapabilityImplementation(
        definition=definicao,
        handler=avaliar_arch003,
        acceptance_tests=[
            AcceptanceTest(
                name="pagina-nao-referenciada-dispara-um-achado",
                entrada=entrada_sucesso,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: len(saida["achados"]) == 1,
            ),
            AcceptanceTest(
                name="pagina-referenciada-nao-dispara",
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
                    "caminho": "pages/x.py",
                    "conteudo": "x",
                    "regra": {"severidade": 123},
                },
                resultado_esperado=ResultadoEsperado.TIMEOUT,
            ),
        ],
    )
