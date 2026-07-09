"""Capability bespoke CS-005 "resposta de erro sem request_id ou
correlation_id" (Vol.IV Cap.17).

Não generalizada em Skill — gate GLOBAL entre uma LISTA DINÂMICA de
arquivos candidatos (`api/middleware/*.py` + `main.py`/`app.py` na raiz
E em `api_dir`) que SUPRIME a regra INTEIRA se QUALQUER um deles tiver
correlation/request/trace id — diferente de PD-011 (2 fontes FIXAS): a
lista de middleware é descoberta por glob, tamanho variável. 1 Missão
por arquivo candidato de `api_dir`, cada uma carregando o texto agregado
do "gate" (computado uma única vez) — mesmo princípio de cardinalidade
invertida de ARCH-003/FE-API."""

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

_ERR_RE = re.compile(
    r"raise HTTPException\s*\(|return JSONResponse\s*\(.*status_code\s*=\s*[45]", re.I
)
_REQID_RE = re.compile(r"request_id|correlation_id|trace_id", re.I)


class RegraCs005Spec(BaseModel):
    codigo: str
    agente: str
    severidade: str
    categoria: str
    titulo: str
    causa: str
    remediacao: str


class EntradaCs005(BaseModel):
    tipo: Literal["cs005"] = "cs005"
    caminho: str
    conteudo: str | None = None
    regra: RegraCs005Spec


class AchadoCs005(BaseModel):
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


class SaidaCs005(BaseModel):
    achados: list[AchadoCs005] = Field(default_factory=list)


class EntradaInvalida(Exception):
    """Levantada quando `entrada` não satisfaz `EntradaCs005` — vira
    SCHEMA_REJECTION no Execution Engine (Vol.III Cap.12)."""


def _computar_fingerprint(agente: str, categoria: str, caminho: str, codigo: str) -> str:
    import hashlib

    normalizado = caminho.replace("\\", "/")
    bruto = f"{agente}|{categoria}|{normalizado}|{codigo}|"
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()


def _fmt_lines(lines: list[int]) -> str:
    return ",".join(str(x) for x in sorted(set(lines)))


def avaliar_cs005(entrada: Any, contexto: ExecutionContext) -> Any:
    del contexto
    try:
        dados = EntradaCs005.model_validate(entrada)
    except Exception as exc:
        raise EntradaInvalida(str(exc)) from exc

    if dados.conteudo is None:
        return SaidaCs005(achados=[]).model_dump()

    payload = json.loads(dados.conteudo)
    api_src: str = payload.get("api_src", "")
    middleware_global_texto: str = payload.get("middleware_global_texto", "")

    if _REQID_RE.search(middleware_global_texto):
        return SaidaCs005(achados=[]).model_dump()

    if not _ERR_RE.search(api_src):
        return SaidaCs005(achados=[]).model_dump()
    if _REQID_RE.search(api_src):
        return SaidaCs005(achados=[]).model_dump()

    lines: list[int] = []
    for lineno, line in enumerate(api_src.splitlines(), 1):
        if _ERR_RE.search(line):
            lines.append(lineno)
    if not lines:
        return SaidaCs005(achados=[]).model_dump()

    regra = dados.regra
    fingerprint = _computar_fingerprint(regra.agente, regra.categoria, dados.caminho, regra.codigo)
    achado = AchadoCs005(
        codigo=regra.codigo,
        agente=regra.agente,
        severidade=regra.severidade,
        categoria=regra.categoria,
        titulo=regra.titulo,
        descricao=(
            f"{dados.caminho}: resposta de erro sem request_id/correlation_id "
            f"(linhas {_fmt_lines(lines)})."
        ),
        causa=regra.causa,
        remediacao=regra.remediacao,
        arquivo=dados.caminho,
        fingerprint=fingerprint,
    )
    return SaidaCs005(achados=[achado]).model_dump()


def construir_implementacao() -> CapabilityImplementation:
    definicao = CapabilityDefinition(
        id=CapabilityId("cs005-erro-sem-request-id"),
        name="CS-005 resposta de erro sem request_id",
        version="1.0.0",
        input_schema=EntradaCs005.model_json_schema(),
        output_schema=SaidaCs005.model_json_schema(),
        deterministic=True,
        side_effects=SideEffects.NONE,
        idempotent=True,
    )

    _regra_teste = {
        "codigo": "CS-005",
        "agente": "customer-success",
        "severidade": "medium",
        "categoria": "rastreabilidade",
        "titulo": "t",
        "causa": "c",
        "remediacao": "r",
    }
    entrada_sucesso = {
        "caminho": "api/routers/pedidos.py",
        "conteudo": json.dumps(
            {
                "api_src": "raise HTTPException(status_code=404)\n",
                "middleware_global_texto": "",
            }
        ),
        "regra": _regra_teste,
    }
    entrada_ok = {
        "caminho": "api/routers/pedidos.py",
        "conteudo": json.dumps(
            {
                "api_src": "raise HTTPException(status_code=404, detail={'request_id': rid})\n",
                "middleware_global_texto": "",
            }
        ),
        "regra": _regra_teste,
    }
    entrada_middleware_global = {
        "caminho": "api/routers/pedidos.py",
        "conteudo": json.dumps(
            {
                "api_src": "raise HTTPException(status_code=404)\n",
                "middleware_global_texto": "def add_request_id(req): pass\n",
            }
        ),
        "regra": _regra_teste,
    }

    return CapabilityImplementation(
        definition=definicao,
        handler=avaliar_cs005,
        acceptance_tests=[
            AcceptanceTest(
                name="erro-sem-request-id-dispara",
                entrada=entrada_sucesso,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: len(saida["achados"]) == 1,
            ),
            AcceptanceTest(
                name="erro-com-request-id-nao-dispara",
                entrada=entrada_ok,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: saida["achados"] == [],
            ),
            AcceptanceTest(
                name="middleware-global-suprime-a-regra-inteira",
                entrada=entrada_middleware_global,
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
