"""Capability bespoke FE-001 "export duplicado entre arquivos" (Vol.IV
Cap.17).

Não generalizada numa Skill — agregação GLOBAL com AGRUPAMENTO: 1 única
Missão recebe TODOS os arquivos de `frontend_api_dir` empacotados (mesmo
princípio de `regex_agregado_multi_arquivo`/ORA-004), mas o handler
constrói um dict nome-exportado → lista de arquivos, e para cada nome
com 2+ arquivos DISTINTOS produz seu PRÓPRIO achado com `chave=nome` e
`caminho=primeiro arquivo em ordem alfabética` (replica
`compute_fingerprint`: `arquivos[0]["path"]` do legado, que é
`sorted(set(files))[0]`). Diferente de FE-API (1 achado por ROTA dentro
de um arquivo já conhecido) e de `regex_agregado_multi_arquivo` (no
máximo 1 achado para TODO o lote, nunca agrupado por chave)."""

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

_EXPORT_RE = re.compile(r"export\s+(?:const|function|class)\s+([A-Za-z0-9_]+)")


class RegraFe001Spec(BaseModel):
    codigo: str
    agente: str
    severidade: str
    categoria: str
    titulo: str
    causa: str
    remediacao: str


class EntradaFe001(BaseModel):
    tipo: Literal["fe001"] = "fe001"
    caminho: str
    conteudo: str | None = None
    regra: RegraFe001Spec


class AchadoFe001(BaseModel):
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


class SaidaFe001(BaseModel):
    achados: list[AchadoFe001] = Field(default_factory=list)


class EntradaInvalida(Exception):
    """Levantada quando `entrada` não satisfaz `EntradaFe001` — vira
    SCHEMA_REJECTION no Execution Engine (Vol.III Cap.12)."""


def _computar_fingerprint(
    agente: str, categoria: str, caminho: str, codigo: str, chave: str
) -> str:
    import hashlib

    normalizado = caminho.replace("\\", "/")
    bruto = f"{agente}|{categoria}|{normalizado}|{codigo}|{chave}"
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()


def avaliar_fe001(entrada: Any, contexto: ExecutionContext) -> Any:
    del contexto
    try:
        dados = EntradaFe001.model_validate(entrada)
    except Exception as exc:
        raise EntradaInvalida(str(exc)) from exc

    payload = json.loads(dados.conteudo) if dados.conteudo else {}
    arquivos: dict[str, str] = payload.get("arquivos", {})

    exports: dict[str, list[str]] = {}
    for caminho, texto in arquivos.items():
        for m in _EXPORT_RE.finditer(texto):
            exports.setdefault(m.group(1), []).append(caminho)

    regra = dados.regra
    achados: list[AchadoFe001] = []
    for nome, arquivos_do_nome in sorted(exports.items()):
        uniq = sorted(set(arquivos_do_nome))
        if len(uniq) <= 1:
            continue
        primario = uniq[0]
        fingerprint = _computar_fingerprint(
            regra.agente, regra.categoria, primario, regra.codigo, nome
        )
        achados.append(
            AchadoFe001(
                codigo=regra.codigo,
                agente=regra.agente,
                severidade=regra.severidade,
                categoria=regra.categoria,
                titulo=regra.titulo,
                descricao=f"'{nome}' exportado em: {', '.join(uniq)}.",
                causa=regra.causa,
                remediacao=regra.remediacao,
                arquivo=primario,
                chave=nome,
                fingerprint=fingerprint,
            )
        )

    return SaidaFe001(achados=achados).model_dump()


def construir_implementacao() -> CapabilityImplementation:
    definicao = CapabilityDefinition(
        id=CapabilityId("fe001-export-duplicado"),
        name="FE-001 export duplicado entre arquivos",
        version="1.0.0",
        input_schema=EntradaFe001.model_json_schema(),
        output_schema=SaidaFe001.model_json_schema(),
        deterministic=True,
        side_effects=SideEffects.NONE,
        idempotent=True,
    )

    _regra_teste = {
        "codigo": "FE-001",
        "agente": "frontend-engineer",
        "severidade": "high",
        "categoria": "api",
        "titulo": "t",
        "causa": "c",
        "remediacao": "r",
    }
    entrada_sucesso = {
        "caminho": "frontend/src/api",
        "conteudo": json.dumps(
            {
                "arquivos": {
                    "frontend/src/api/a.ts": "export const adminApi = {}\n",
                    "frontend/src/api/b.ts": "export const adminApi = {}\n",
                }
            }
        ),
        "regra": _regra_teste,
    }
    entrada_ok = {
        "caminho": "frontend/src/api",
        "conteudo": json.dumps(
            {
                "arquivos": {
                    "frontend/src/api/a.ts": "export const userApi = {}\n",
                    "frontend/src/api/b.ts": "export const adminApi = {}\n",
                }
            }
        ),
        "regra": _regra_teste,
    }

    return CapabilityImplementation(
        definition=definicao,
        handler=avaliar_fe001,
        acceptance_tests=[
            AcceptanceTest(
                name="export-duplicado-em-2-arquivos-dispara-um-achado",
                entrada=entrada_sucesso,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: len(saida["achados"]) == 1,
            ),
            AcceptanceTest(
                name="exports-unicos-nao-disparam",
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
                    "caminho": "frontend/src/api",
                    "conteudo": "x",
                    "regra": {"severidade": 123},
                },
                resultado_esperado=ResultadoEsperado.TIMEOUT,
            ),
        ],
    )
