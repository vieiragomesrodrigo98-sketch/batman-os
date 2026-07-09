"""Capability bespoke PD-010 "simulador de carteira sem bloqueio de saldo
mínimo" (Vol.IV Cap.17).

Não generalizada em Skill — DOIS sub-checks INDEPENDENTES na mesma
regra, cada um sobre um CONJUNTO DE ARQUIVOS diferente (backend: 1
arquivo fixo `api/routers/sim.py`; frontend: N arquivos filtrados por
nome contendo "sim"), cada achado com seu PRÓPRIO `caminho` (não
colapsam — múltiplos achados reais possíveis, um por arquivo elegível).
O handler distingue o modo comparando `dados.caminho` contra
`regra.sim_router_path`."""

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

_HAS_FLOOR_BACKEND = re.compile(r"MIN_TRADE_CAPITAL|saldo.*mínimo|mínimo.*saldo", re.I)
_HAS_FLOOR_FRONTEND = re.compile(
    r"balance.*MIN|MIN.*balance|Saldo insuficiente|disabled.*balance", re.I
)
_HAS_BALANCE_MENTION = re.compile(r"balance|saldo", re.I)


class RegraPd010Spec(BaseModel):
    codigo: str
    agente: str
    severidade: str
    categoria: str
    titulo: str
    causa: str
    remediacao: str
    sim_router_path: str = "api/routers/sim.py"


class EntradaPd010(BaseModel):
    tipo: Literal["pd010"] = "pd010"
    caminho: str
    conteudo: str | None = None
    regra: RegraPd010Spec


class AchadoPd010(BaseModel):
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


class SaidaPd010(BaseModel):
    achados: list[AchadoPd010] = Field(default_factory=list)


class EntradaInvalida(Exception):
    """Levantada quando `entrada` não satisfaz `EntradaPd010` — vira
    SCHEMA_REJECTION no Execution Engine (Vol.III Cap.12)."""


def _computar_fingerprint(agente: str, categoria: str, caminho: str, codigo: str) -> str:
    import hashlib

    normalizado = caminho.replace("\\", "/")
    bruto = f"{agente}|{categoria}|{normalizado}|{codigo}|"
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()


def avaliar_pd010(entrada: Any, contexto: ExecutionContext) -> Any:
    del contexto
    try:
        dados = EntradaPd010.model_validate(entrada)
    except Exception as exc:
        raise EntradaInvalida(str(exc)) from exc

    if dados.conteudo is None:
        return SaidaPd010(achados=[]).model_dump()

    regra = dados.regra
    caminho_normalizado = dados.caminho.replace("\\", "/")
    is_backend = caminho_normalizado == regra.sim_router_path.replace("\\", "/")

    if is_backend:
        if _HAS_FLOOR_BACKEND.search(dados.conteudo):
            return SaidaPd010(achados=[]).model_dump()
        descricao = (
            f"{dados.caminho}: sem constante de saldo mínimo — "
            "usuário pode abrir posições com R$0,01."
        )
    else:
        if not _HAS_BALANCE_MENTION.search(dados.conteudo):
            return SaidaPd010(achados=[]).model_dump()
        if _HAS_FLOOR_FRONTEND.search(dados.conteudo):
            return SaidaPd010(achados=[]).model_dump()
        descricao = (
            f"{dados.caminho}: componente de simulador não desabilita ação quando "
            "saldo insuficiente."
        )

    fingerprint = _computar_fingerprint(regra.agente, regra.categoria, dados.caminho, regra.codigo)
    achado = AchadoPd010(
        codigo=regra.codigo,
        agente=regra.agente,
        severidade=regra.severidade,
        categoria=regra.categoria,
        titulo=regra.titulo,
        descricao=descricao,
        causa=regra.causa,
        remediacao=regra.remediacao,
        arquivo=dados.caminho,
        fingerprint=fingerprint,
    )
    return SaidaPd010(achados=[achado]).model_dump()


def construir_implementacao() -> CapabilityImplementation:
    definicao = CapabilityDefinition(
        id=CapabilityId("pd010-simulador-sem-piso"),
        name="PD-010 simulador sem bloqueio de saldo minimo",
        version="1.0.0",
        input_schema=EntradaPd010.model_json_schema(),
        output_schema=SaidaPd010.model_json_schema(),
        deterministic=True,
        side_effects=SideEffects.NONE,
        idempotent=True,
    )

    _regra_teste = {
        "codigo": "PD-010",
        "agente": "product-designer",
        "severidade": "medium",
        "categoria": "regra-de-negocio",
        "titulo": "t",
        "causa": "c",
        "remediacao": "r",
        "sim_router_path": "api/routers/sim.py",
    }
    entrada_sucesso = {
        "caminho": "api/routers/sim.py",
        "conteudo": "def abrir_posicao():\n    pass\n",
        "regra": _regra_teste,
    }
    entrada_ok = {
        "caminho": "api/routers/sim.py",
        "conteudo": "MIN_TRADE_CAPITAL = 10\n",
        "regra": _regra_teste,
    }

    return CapabilityImplementation(
        definition=definicao,
        handler=avaliar_pd010,
        acceptance_tests=[
            AcceptanceTest(
                name="backend-sem-piso-de-saldo-dispara",
                entrada=entrada_sucesso,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: len(saida["achados"]) == 1,
            ),
            AcceptanceTest(
                name="backend-com-piso-de-saldo-nao-dispara",
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
                    "caminho": "api/routers/sim.py",
                    "conteudo": "x",
                    "regra": {"severidade": 123},
                },
                resultado_esperado=ResultadoEsperado.TIMEOUT,
            ),
        ],
    )
