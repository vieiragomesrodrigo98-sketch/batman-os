"""Capability bespoke CTO-004 "endpoint sem docstring nem response_model
declarado" (Vol.IV Cap.17).

Não generalizada em Skill — máquina de estados por linha com MÚLTIPLOS
passos sequenciais (acha linha do decorator → verifica response_model na
janela → acha linha do `def`/`async def` → acha fim da assinatura (linha
terminando em `:`) → verifica docstring nas até-3-linhas seguintes) — não
é um único padrão regex nem uma janela fixa em torno de UMA âncora, é uma
sequência de buscas por landmarks distintos."""

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

_DECORATOR_LINE_RE = re.compile(r"@(?:router|app)\.(get|post|put|patch|delete)\s*\(")
_RESPONSE_MODEL_RE = re.compile(r"response_model\s*=")


class RegraCto004Spec(BaseModel):
    codigo: str
    agente: str
    severidade: str
    categoria: str
    titulo: str
    causa: str
    remediacao: str


class EntradaCto004(BaseModel):
    tipo: Literal["cto004"] = "cto004"
    caminho: str
    conteudo: str | None = None
    regra: RegraCto004Spec


class AchadoCto004(BaseModel):
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


class SaidaCto004(BaseModel):
    achados: list[AchadoCto004] = Field(default_factory=list)


class EntradaInvalida(Exception):
    """Levantada quando `entrada` não satisfaz `EntradaCto004` — vira
    SCHEMA_REJECTION no Execution Engine (Vol.III Cap.12)."""


def _computar_fingerprint(agente: str, categoria: str, caminho: str, codigo: str) -> str:
    import hashlib

    normalizado = caminho.replace("\\", "/")
    bruto = f"{agente}|{categoria}|{normalizado}|{codigo}|"
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()


def _linhas_sem_doc_ou_response_model(text: str) -> list[int]:
    lines = text.splitlines()
    achadas: list[int] = []

    for i, line in enumerate(lines):
        if not _DECORATOR_LINE_RE.search(line):
            continue
        if _RESPONSE_MODEL_RE.search(line):
            continue
        decorator_block = "\n".join(lines[i : i + 5])
        if _RESPONSE_MODEL_RE.search(decorator_block):
            continue

        func_line_idx = None
        for j in range(i + 1, min(i + 6, len(lines))):
            stripped = lines[j].strip()
            if stripped.startswith("def ") or stripped.startswith("async def "):
                func_line_idx = j
                break
        if func_line_idx is None:
            continue

        sig_end = func_line_idx
        for j in range(func_line_idx, min(func_line_idx + 20, len(lines))):
            if lines[j].rstrip().endswith(":"):
                sig_end = j
                break

        body_start = sig_end + 1
        has_docstring = False
        for k in range(body_start, min(body_start + 3, len(lines))):
            stripped = lines[k].strip()
            if stripped.startswith('"""') or stripped.startswith("'''"):
                has_docstring = True
                break
            if stripped and not stripped.startswith("#"):
                break

        if not has_docstring:
            achadas.append(i + 1)

    return achadas


def avaliar_cto004(entrada: Any, contexto: ExecutionContext) -> Any:
    del contexto
    try:
        dados = EntradaCto004.model_validate(entrada)
    except Exception as exc:
        raise EntradaInvalida(str(exc)) from exc

    if dados.conteudo is None:
        return SaidaCto004(achados=[]).model_dump()

    linhas = _linhas_sem_doc_ou_response_model(dados.conteudo)
    if not linhas:
        return SaidaCto004(achados=[]).model_dump()

    regra = dados.regra
    achados: list[AchadoCto004] = []
    for linha in linhas:
        fingerprint = _computar_fingerprint(
            regra.agente, regra.categoria, dados.caminho, regra.codigo
        )
        achados.append(
            AchadoCto004(
                codigo=regra.codigo,
                agente=regra.agente,
                severidade=regra.severidade,
                categoria=regra.categoria,
                titulo=regra.titulo,
                descricao=(
                    f"{dados.caminho}: endpoint sem docstring nem response_model (linha {linha})."
                ),
                causa=regra.causa,
                remediacao=regra.remediacao,
                arquivo=dados.caminho,
                fingerprint=fingerprint,
            )
        )

    return SaidaCto004(achados=achados).model_dump()


def construir_implementacao() -> CapabilityImplementation:
    definicao = CapabilityDefinition(
        id=CapabilityId("cto004-endpoint-sem-doc"),
        name="CTO-004 endpoint sem docstring nem response_model",
        version="1.0.0",
        input_schema=EntradaCto004.model_json_schema(),
        output_schema=SaidaCto004.model_json_schema(),
        deterministic=True,
        side_effects=SideEffects.NONE,
        idempotent=True,
    )

    _regra_teste = {
        "codigo": "CTO-004",
        "agente": "cto",
        "severidade": "low",
        "categoria": "api-design",
        "titulo": "t",
        "causa": "c",
        "remediacao": "r",
    }
    entrada_sucesso = {
        "caminho": "api/routers/pedidos.py",
        "conteudo": ("@router.get('/pedidos')\ndef listar():\n    return []\n"),
        "regra": _regra_teste,
    }
    entrada_ok = {
        "caminho": "api/routers/pedidos.py",
        "conteudo": (
            '@router.get(\'/pedidos\')\ndef listar():\n    """Lista pedidos."""\n    return []\n'
        ),
        "regra": _regra_teste,
    }

    return CapabilityImplementation(
        definition=definicao,
        handler=avaliar_cto004,
        acceptance_tests=[
            AcceptanceTest(
                name="endpoint-sem-doc-nem-response-model-dispara",
                entrada=entrada_sucesso,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: len(saida["achados"]) == 1,
            ),
            AcceptanceTest(
                name="endpoint-com-docstring-nao-dispara",
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
