"""Capability bespoke PD-011 "diversificação do motor não comunicada"
(Vol.IV Cap.17).

Não generalizada numa Skill — combinação ASSIMÉTRICA entre DUAS fontes
agregadas distintas: dispara quando o padrão está PRESENTE no backend
(`src/**/*.py`) E AUSENTE no frontend (`frontend_dirs`). Diferente de
LEGAL-002 (`regex_agregado_multi_arquivo` com `pattern_2` — OR simétrico
de ausência dentro da MESMA fonte combinada): aqui as duas fontes
precisam ser avaliadas SEPARADAMENTE, não misturadas num texto único,
porque a condição depende de ONDE o padrão aparece (backend vs.
frontend), não apenas SE aparece."""

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


class RegraPd011Spec(BaseModel):
    codigo: str
    agente: str
    severidade: str
    categoria: str
    titulo: str
    causa: str
    remediacao: str
    pattern: str
    ignore_case: bool = False


class EntradaPd011(BaseModel):
    tipo: Literal["pd011"] = "pd011"
    caminho: str
    conteudo: str | None = None
    regra: RegraPd011Spec


class AchadoPd011(BaseModel):
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


class SaidaPd011(BaseModel):
    achados: list[AchadoPd011] = Field(default_factory=list)


class EntradaInvalida(Exception):
    """Levantada quando `entrada` não satisfaz `EntradaPd011` — vira
    SCHEMA_REJECTION no Execution Engine (Vol.III Cap.12)."""


def _computar_fingerprint(agente: str, categoria: str, caminho: str, codigo: str) -> str:
    import hashlib

    normalizado = caminho.replace("\\", "/")
    bruto = f"{agente}|{categoria}|{normalizado}|{codigo}|"
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()


def avaliar_pd011(entrada: Any, contexto: ExecutionContext) -> Any:
    del contexto
    try:
        dados = EntradaPd011.model_validate(entrada)
    except Exception as exc:
        raise EntradaInvalida(str(exc)) from exc

    payload = json.loads(dados.conteudo) if dados.conteudo else {}
    frontend_text: str = payload.get("frontend_text", "")
    backend_text: str = payload.get("backend_text", "")

    regra = dados.regra
    flags = re.IGNORECASE if regra.ignore_case else 0

    if re.search(regra.pattern, frontend_text, flags):
        return SaidaPd011(achados=[]).model_dump()
    if not re.search(regra.pattern, backend_text, flags):
        return SaidaPd011(achados=[]).model_dump()

    fingerprint = _computar_fingerprint(regra.agente, regra.categoria, dados.caminho, regra.codigo)
    achado = AchadoPd011(
        codigo=regra.codigo,
        agente=regra.agente,
        severidade=regra.severidade,
        categoria=regra.categoria,
        titulo=regra.titulo,
        descricao=f"{dados.caminho}: {regra.titulo}",
        causa=regra.causa,
        remediacao=regra.remediacao,
        arquivo=dados.caminho,
        fingerprint=fingerprint,
    )
    return SaidaPd011(achados=[achado]).model_dump()


def construir_implementacao() -> CapabilityImplementation:
    definicao = CapabilityDefinition(
        id=CapabilityId("pd011-diversificacao-nao-comunicada"),
        name="PD-011 diversificacao do motor nao comunicada",
        version="1.0.0",
        input_schema=EntradaPd011.model_json_schema(),
        output_schema=SaidaPd011.model_json_schema(),
        deterministic=True,
        side_effects=SideEffects.NONE,
        idempotent=True,
    )

    _regra_teste = {
        "codigo": "PD-011",
        "agente": "product-designer",
        "severidade": "low",
        "categoria": "regra-de-negocio",
        "titulo": "t",
        "causa": "c",
        "remediacao": "r",
        "pattern": "MOTOR_CAP01|diversif",
        "ignore_case": True,
    }
    entrada_sucesso = {
        "caminho": "frontend/src/",
        "conteudo": json.dumps(
            {"frontend_text": "nada relacionado", "backend_text": "def diversify(): pass"}
        ),
        "regra": _regra_teste,
    }
    entrada_ok = {
        "caminho": "frontend/src/",
        "conteudo": json.dumps(
            {"frontend_text": "tooltip diversificacao", "backend_text": "def diversify(): pass"}
        ),
        "regra": _regra_teste,
    }

    return CapabilityImplementation(
        definition=definicao,
        handler=avaliar_pd011,
        acceptance_tests=[
            AcceptanceTest(
                name="regra-ativa-no-backend-sem-comunicacao-no-frontend-dispara",
                entrada=entrada_sucesso,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: len(saida["achados"]) == 1,
            ),
            AcceptanceTest(
                name="regra-comunicada-no-frontend-nao-dispara",
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
                    "caminho": "frontend/src/",
                    "conteudo": "x",
                    "regra": {"severidade": 123},
                },
                resultado_esperado=ResultadoEsperado.TIMEOUT,
            ),
        ],
    )
