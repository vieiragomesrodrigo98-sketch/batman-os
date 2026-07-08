"""Capability bespoke BE-013 "HTTP 200 em bloco except" (Vol.IV Cap.17).

Não generalizada numa Skill — máquina de estados por INDENTAÇÃO (não
AST): percorre linha a linha, entra em estado `in_except` ao encontrar
`except[\\s:\\(]` na linha stripada (guardando a indentação do próprio
`except`), permanece nesse estado enquanto as linhas seguintes tiverem
indentação MAIOR que a do `except` (corpo do bloco) — dedent de volta ao
nível do `except` (ou menor) encerra o estado. Dispara para
`status_code=200` encontrado DENTRO do estado `in_except`. Diferente de
`ast_padrao_ausente`/`janela_contexto_regex`: não é seleção por nó AST
nem janela fixa de N linhas — é rastreamento de bloco por indentação, de
extensão variável."""

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

_EXCEPT_ANYWHERE = re.compile(r"except\s*[:(]|except\s+\w")
_EXCEPT_LINE = re.compile(r"except[\s:(]")
_STATUS_200 = re.compile(r"status_code\s*=\s*200")


class RegraBe013Spec(BaseModel):
    codigo: str
    agente: str
    severidade: str
    categoria: str
    titulo: str
    causa: str
    remediacao: str


class EntradaBe013(BaseModel):
    tipo: Literal["be013"] = "be013"
    caminho: str
    conteudo: str | None = None
    regra: RegraBe013Spec


class AchadoBe013(BaseModel):
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


class SaidaBe013(BaseModel):
    achados: list[AchadoBe013] = Field(default_factory=list)


class EntradaInvalida(Exception):
    """Levantada quando `entrada` não satisfaz `EntradaBe013` — vira
    SCHEMA_REJECTION no Execution Engine (Vol.III Cap.12)."""


def _computar_fingerprint(agente: str, categoria: str, caminho: str, codigo: str) -> str:
    import hashlib

    normalizado = caminho.replace("\\", "/")
    bruto = f"{agente}|{categoria}|{normalizado}|{codigo}|"
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()


def _linhas_com_200_em_except(texto: str) -> list[int]:
    if not _EXCEPT_ANYWHERE.search(texto):
        return []

    flagged: list[int] = []
    in_except = False
    except_indent = 0
    for i, line in enumerate(texto.splitlines(), 1):
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if _EXCEPT_LINE.match(stripped):
            in_except = True
            except_indent = indent
            continue
        if in_except:
            if stripped and not stripped.startswith("#") and indent <= except_indent:
                in_except = False
            if in_except and _STATUS_200.search(line):
                flagged.append(i)
    return flagged


def avaliar_be013(entrada: Any, contexto: ExecutionContext) -> Any:
    del contexto
    try:
        dados = EntradaBe013.model_validate(entrada)
    except Exception as exc:
        raise EntradaInvalida(str(exc)) from exc

    flagged = _linhas_com_200_em_except(dados.conteudo or "")
    if not flagged:
        return SaidaBe013(achados=[]).model_dump()

    regra = dados.regra
    fingerprint = _computar_fingerprint(regra.agente, regra.categoria, dados.caminho, regra.codigo)
    linhas = ",".join(str(n) for n in flagged)
    achado = AchadoBe013(
        codigo=regra.codigo,
        agente=regra.agente,
        severidade=regra.severidade,
        categoria=regra.categoria,
        titulo=regra.titulo,
        descricao=f"{dados.caminho}: status_code=200 dentro de bloco except (linhas {linhas}).",
        causa=regra.causa,
        remediacao=regra.remediacao,
        arquivo=dados.caminho,
        fingerprint=fingerprint,
    )
    return SaidaBe013(achados=[achado]).model_dump()


def construir_implementacao() -> CapabilityImplementation:
    definicao = CapabilityDefinition(
        id=CapabilityId("be013-http200-em-except"),
        name="BE-013 HTTP 200 em except",
        version="1.0.0",
        input_schema=EntradaBe013.model_json_schema(),
        output_schema=SaidaBe013.model_json_schema(),
        deterministic=True,
        side_effects=SideEffects.NONE,
        idempotent=True,
    )

    _regra_teste = {
        "codigo": "BE-013",
        "agente": "backend-engineer",
        "severidade": "high",
        "categoria": "api",
        "titulo": "t",
        "causa": "c",
        "remediacao": "r",
    }
    entrada_sucesso = {
        "caminho": "api/x.py",
        "conteudo": (
            "try:\n"
            "    fazer_algo()\n"
            "except Exception:\n"
            "    return JSONResponse(status_code=200, content={'erro': True})\n"
        ),
        "regra": _regra_teste,
    }
    entrada_ok = {
        "caminho": "api/y.py",
        "conteudo": (
            "try:\n"
            "    fazer_algo()\n"
            "except Exception:\n"
            "    return JSONResponse(status_code=500, content={'erro': True})\n"
            "return JSONResponse(status_code=200)\n"
        ),
        "regra": _regra_teste,
    }

    return CapabilityImplementation(
        definition=definicao,
        handler=avaliar_be013,
        acceptance_tests=[
            AcceptanceTest(
                name="status-200-dentro-de-except-dispara-um-achado",
                entrada=entrada_sucesso,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: len(saida["achados"]) == 1,
            ),
            AcceptanceTest(
                name="status-200-fora-do-except-apos-dedent-nao-dispara",
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
                entrada={"caminho": "a.py", "conteudo": "x", "regra": {"severidade": 123}},
                resultado_esperado=ResultadoEsperado.TIMEOUT,
            ),
        ],
    )
