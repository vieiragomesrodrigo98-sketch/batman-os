"""Capability bespoke CS-003 "bloco except silencioso que engole exceções
(pass ou só log)" (Vol.IV Cap.17).

Não reaproveita SUP-001 (`sup001_excecao_silenciada.py`) apesar da
semelhança superficial — SUP-001 tem safelist de tipos de exceção
(`ImportError`/`ModuleNotFoundError`/`HTTPException` são aceitáveis sem
log) e checa log/print/raise/exc-guardado-para-reraise; CS-003 é
incondicional: QUALQUER `ExceptHandler` cujo corpo seja exatamente
`[ast.Pass]` dispara, sem safelist. São regras DIFERENTES que podem
ambas disparar na mesma linha (códigos distintos, achados distintos) —
não a mesma regra com nomes diferentes."""

from __future__ import annotations

import ast
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


class RegraCs003Spec(BaseModel):
    codigo: str
    agente: str
    severidade: str
    categoria: str
    titulo: str
    causa: str
    remediacao: str


class EntradaCs003(BaseModel):
    tipo: Literal["cs003"] = "cs003"
    caminho: str
    conteudo: str | None = None
    regra: RegraCs003Spec


class AchadoCs003(BaseModel):
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


class SaidaCs003(BaseModel):
    achados: list[AchadoCs003] = Field(default_factory=list)


class EntradaInvalida(Exception):
    """Levantada quando `entrada` não satisfaz `EntradaCs003` — vira
    SCHEMA_REJECTION no Execution Engine (Vol.III Cap.12)."""


def _computar_fingerprint(agente: str, categoria: str, caminho: str, codigo: str) -> str:
    import hashlib

    normalizado = caminho.replace("\\", "/")
    bruto = f"{agente}|{categoria}|{normalizado}|{codigo}|"
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()


def _dispara(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
            return True
    return False


def avaliar_cs003(entrada: Any, contexto: ExecutionContext) -> Any:
    del contexto
    try:
        dados = EntradaCs003.model_validate(entrada)
    except Exception as exc:
        raise EntradaInvalida(str(exc)) from exc

    if dados.conteudo is None:
        return SaidaCs003(achados=[]).model_dump()

    try:
        tree = ast.parse(dados.conteudo)
    except SyntaxError:
        return SaidaCs003(achados=[]).model_dump()

    if not _dispara(tree):
        return SaidaCs003(achados=[]).model_dump()

    regra = dados.regra
    fingerprint = _computar_fingerprint(regra.agente, regra.categoria, dados.caminho, regra.codigo)
    achado = AchadoCs003(
        codigo=regra.codigo,
        agente=regra.agente,
        severidade=regra.severidade,
        categoria=regra.categoria,
        titulo=regra.titulo,
        descricao=f"{dados.caminho}: except com pass silencia exceção.",
        causa=regra.causa,
        remediacao=regra.remediacao,
        arquivo=dados.caminho,
        fingerprint=fingerprint,
    )
    return SaidaCs003(achados=[achado]).model_dump()


def construir_implementacao() -> CapabilityImplementation:
    definicao = CapabilityDefinition(
        id=CapabilityId("cs003-except-pass"),
        name="CS-003 except com pass silencia excecao",
        version="1.0.0",
        input_schema=EntradaCs003.model_json_schema(),
        output_schema=SaidaCs003.model_json_schema(),
        deterministic=True,
        side_effects=SideEffects.NONE,
        idempotent=True,
    )

    _regra_teste = {
        "codigo": "CS-003",
        "agente": "customer-success",
        "severidade": "medium",
        "categoria": "estabilidade",
        "titulo": "t",
        "causa": "c",
        "remediacao": "r",
    }
    entrada_sucesso = {
        "caminho": "api/x.py",
        "conteudo": "try:\n    f()\nexcept Exception:\n    pass\n",
        "regra": _regra_teste,
    }
    entrada_ok = {
        "caminho": "api/x.py",
        "conteudo": "try:\n    f()\nexcept Exception as e:\n    log.error(e)\n    raise\n",
        "regra": _regra_teste,
    }

    return CapabilityImplementation(
        definition=definicao,
        handler=avaliar_cs003,
        acceptance_tests=[
            AcceptanceTest(
                name="except-com-pass-dispara",
                entrada=entrada_sucesso,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: len(saida["achados"]) == 1,
            ),
            AcceptanceTest(
                name="except-com-tratamento-nao-dispara",
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
