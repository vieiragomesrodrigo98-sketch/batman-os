"""Capability bespoke GOVDEBT-001 "finding aberto sem decisão há 2+
sessões" (Vol.IV Cap.17).

Não generalizada em Skill — lê estado INTERNO do próprio Batman
(`Batman/ledger.json` + `Batman/config/deferred.json`), não código do
usuário. Agregação GLOBAL com AGRUPAMENTO (mesmo princípio de FE-001):
1 única Missão empacota os DOIS arquivos, o handler produz 1 achado POR
finding do ledger elegível, com `chave=fp` (o fingerprint ORIGINAL do
ledger — replica `yield ... chave=fp` do legado, que torna o fingerprint
GOVDEBT estável por finding subjacente)."""

from __future__ import annotations

import json
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

_SESSIONS_THRESHOLD = 2


class RegraGovdebt001Spec(BaseModel):
    codigo: str
    agente: str
    severidade: str
    categoria: str
    titulo: str
    causa: str
    remediacao: str


class EntradaGovdebt001(BaseModel):
    tipo: Literal["govdebt001"] = "govdebt001"
    caminho: str
    conteudo: str | None = None
    regra: RegraGovdebt001Spec


class AchadoGovdebt001(BaseModel):
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


class SaidaGovdebt001(BaseModel):
    achados: list[AchadoGovdebt001] = Field(default_factory=list)


class EntradaInvalida(Exception):
    """Levantada quando `entrada` não satisfaz `EntradaGovdebt001` — vira
    SCHEMA_REJECTION no Execution Engine (Vol.III Cap.12)."""


def _computar_fingerprint(
    agente: str, categoria: str, caminho: str, codigo: str, chave: str
) -> str:
    import hashlib

    normalizado = caminho.replace("\\", "/")
    bruto = f"{agente}|{categoria}|{normalizado}|{codigo}|{chave}"
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()


def avaliar_govdebt001(entrada: Any, contexto: ExecutionContext) -> Any:
    del contexto
    try:
        dados = EntradaGovdebt001.model_validate(entrada)
    except Exception as exc:
        raise EntradaInvalida(str(exc)) from exc

    if dados.conteudo is None:
        return SaidaGovdebt001(achados=[]).model_dump()

    payload = json.loads(dados.conteudo)
    ledger: dict[str, Any] | None = payload.get("ledger")
    if ledger is None:
        return SaidaGovdebt001(achados=[]).model_dump()

    deferred_codes: set[str] = set(payload.get("deferred_codes", []))

    regra = dados.regra
    achados: list[AchadoGovdebt001] = []
    for fp, entry in ledger.get("entries", {}).items():
        if entry.get("status") != "open":
            continue
        if entry.get("sessoes_aberto", 0) < _SESSIONS_THRESHOLD:
            continue
        codigo = entry.get("codigo", "")
        if codigo.startswith("GOVDEBT"):
            continue
        if codigo in deferred_codes:
            continue

        sessoes = entry["sessoes_aberto"]
        agente_orig = entry.get("agente", "?")
        titulo_orig = entry.get("titulo", "?")[:60]
        descricao_orig = entry.get("descricao", "")[:100]

        descricao = (
            f"{codigo} ({agente_orig}) aberto há {sessoes} sessões sem fix nem "
            f"deferimento: {titulo_orig}. Achado: {descricao_orig}"
        )
        fingerprint = _computar_fingerprint(
            regra.agente, regra.categoria, dados.caminho, regra.codigo, fp
        )
        achados.append(
            AchadoGovdebt001(
                codigo=regra.codigo,
                agente=regra.agente,
                severidade=regra.severidade,
                categoria=regra.categoria,
                titulo=regra.titulo,
                descricao=descricao,
                causa=regra.causa,
                remediacao=regra.remediacao,
                arquivo=dados.caminho,
                chave=fp,
                fingerprint=fingerprint,
            )
        )

    return SaidaGovdebt001(achados=achados).model_dump()


def construir_implementacao() -> CapabilityImplementation:
    definicao = CapabilityDefinition(
        id=CapabilityId("govdebt001-finding-sem-decisao"),
        name="GOVDEBT-001 finding aberto sem decisao ha 2+ sessoes",
        version="1.0.0",
        input_schema=EntradaGovdebt001.model_json_schema(),
        output_schema=SaidaGovdebt001.model_json_schema(),
        deterministic=True,
        side_effects=SideEffects.NONE,
        idempotent=True,
    )

    _regra_teste = {
        "codigo": "GOVDEBT-001",
        "agente": "governance-debt",
        "severidade": "high",
        "categoria": "governanca",
        "titulo": "t",
        "causa": "c",
        "remediacao": "r",
    }
    entrada_sucesso = {
        "caminho": "Batman/ledger.json",
        "conteudo": json.dumps(
            {
                "ledger": {
                    "entries": {
                        "abcdef0123456789": {
                            "status": "open",
                            "sessoes_aberto": 3,
                            "codigo": "SEC-001",
                            "agente": "security-engineer",
                            "titulo": "t",
                            "descricao": "d",
                        }
                    }
                },
                "deferred_codes": [],
            }
        ),
        "regra": _regra_teste,
    }
    entrada_ok = {
        "caminho": "Batman/ledger.json",
        "conteudo": json.dumps(
            {
                "ledger": {
                    "entries": {
                        "abcdef0123456789": {
                            "status": "open",
                            "sessoes_aberto": 3,
                            "codigo": "SEC-001",
                            "agente": "security-engineer",
                            "titulo": "t",
                            "descricao": "d",
                        }
                    }
                },
                "deferred_codes": ["SEC-001"],
            }
        ),
        "regra": _regra_teste,
    }

    return CapabilityImplementation(
        definition=definicao,
        handler=avaliar_govdebt001,
        acceptance_tests=[
            AcceptanceTest(
                name="finding-aberto-2-sessoes-sem-deferimento-dispara",
                entrada=entrada_sucesso,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: len(saida["achados"]) == 1,
            ),
            AcceptanceTest(
                name="finding-deferido-nao-dispara",
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
                    "caminho": "Batman/ledger.json",
                    "conteudo": "x",
                    "regra": {"severidade": 123},
                },
                resultado_esperado=ResultadoEsperado.TIMEOUT,
            ),
        ],
    )
