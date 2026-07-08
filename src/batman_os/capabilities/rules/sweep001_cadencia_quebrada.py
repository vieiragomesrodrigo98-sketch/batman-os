"""Capability bespoke SWEEP-001 "rodízio de sweeps por skill fora da
cadência" (Vol.IV Cap.17).

Não generalizada em Skill — lê estado INTERNO do próprio Batman
(`Batman/config/sweep_state.json`), não código do usuário, E depende do
RELÓGIO ATUAL (`datetime.now(UTC)` comparado a `atribuido_em` do estado)
— única Capability desta migração cujo resultado varia com O MOMENTO em
que o scan roda, não só com o conteúdo do repositório (replica
`rotation.dias_atribuido` do legado)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
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

_CADENCIA_DIAS_PADRAO = 7


class RegraSweep001Spec(BaseModel):
    codigo: str
    agente: str
    severidade: str
    categoria: str
    titulo: str
    causa: str
    remediacao: str


class EntradaSweep001(BaseModel):
    tipo: Literal["sweep001"] = "sweep001"
    caminho: str
    conteudo: str | None = None
    regra: RegraSweep001Spec


class AchadoSweep001(BaseModel):
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


class SaidaSweep001(BaseModel):
    achados: list[AchadoSweep001] = Field(default_factory=list)


class EntradaInvalida(Exception):
    """Levantada quando `entrada` não satisfaz `EntradaSweep001` — vira
    SCHEMA_REJECTION no Execution Engine (Vol.III Cap.12)."""


def _computar_fingerprint(
    agente: str, categoria: str, caminho: str, codigo: str, chave: str
) -> str:
    import hashlib

    normalizado = caminho.replace("\\", "/")
    bruto = f"{agente}|{categoria}|{normalizado}|{codigo}|{chave}"
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()


def _dias_atribuido(state: dict[str, Any]) -> int:
    atual = state.get("atual") or {}
    try:
        atribuido = datetime.fromisoformat(atual["atribuido_em"])
    except Exception:
        return 0
    return max(0, (datetime.now(UTC) - atribuido).days)


def _achado(regra: RegraSweep001Spec, caminho: str, chave: str, descricao: str) -> AchadoSweep001:
    fingerprint = _computar_fingerprint(regra.agente, regra.categoria, caminho, regra.codigo, chave)
    return AchadoSweep001(
        codigo=regra.codigo,
        agente=regra.agente,
        severidade=regra.severidade,
        categoria=regra.categoria,
        titulo=regra.titulo,
        descricao=descricao,
        causa=regra.causa,
        remediacao=regra.remediacao,
        arquivo=caminho,
        chave=chave,
        fingerprint=fingerprint,
    )


def avaliar_sweep001(entrada: Any, contexto: ExecutionContext) -> Any:
    del contexto
    try:
        dados = EntradaSweep001.model_validate(entrada)
    except Exception as exc:
        raise EntradaInvalida(str(exc)) from exc

    regra = dados.regra

    if dados.conteudo is None:
        achado = _achado(
            regra,
            dados.caminho,
            "nao-inicializado",
            "rotação de sweeps não inicializada — rode: python -m Batman.cli.batman sweep init",
        )
        return SaidaSweep001(achados=[achado]).model_dump()

    state = json.loads(dados.conteudo)

    atual = state.get("atual")
    if not atual:
        achado = _achado(
            regra,
            dados.caminho,
            "parado",
            "rotação de sweeps parada (sem papel atribuído) — rode: batman sweep init",
        )
        return SaidaSweep001(achados=[achado]).model_dump()

    cad = state.get("cadencia_dias", _CADENCIA_DIAS_PADRAO)
    dias = _dias_atribuido(state)
    if dias > cad:
        papel = atual.get("papel", "?")
        descricao = (
            f"missão de sweep '{papel}' atribuída há {dias}d (cadência {cad}d) "
            f"sem conclusão — status '{atual.get('status', '?')}'"
        )
        achado = _achado(regra, dados.caminho, papel, descricao)
        return SaidaSweep001(achados=[achado]).model_dump()

    return SaidaSweep001(achados=[]).model_dump()


def construir_implementacao() -> CapabilityImplementation:
    definicao = CapabilityDefinition(
        id=CapabilityId("sweep001-cadencia-quebrada"),
        name="SWEEP-001 rodizio de sweeps fora da cadencia",
        version="1.0.0",
        input_schema=EntradaSweep001.model_json_schema(),
        output_schema=SaidaSweep001.model_json_schema(),
        deterministic=True,
        side_effects=SideEffects.NONE,
        idempotent=True,
    )

    _regra_teste = {
        "codigo": "SWEEP-001",
        "agente": "skill-sweep",
        "severidade": "medium",
        "categoria": "governanca",
        "titulo": "t",
        "causa": "c",
        "remediacao": "r",
    }
    entrada_sucesso = {
        "caminho": "Batman/config/sweep_state.json",
        "conteudo": None,
        "regra": _regra_teste,
    }
    entrada_ok = {
        "caminho": "Batman/config/sweep_state.json",
        "conteudo": json.dumps(
            {
                "cadencia_dias": 7,
                "atual": {
                    "papel": "security-engineer",
                    "atribuido_em": datetime.now(UTC).isoformat(),
                    "status": "pendente",
                },
            }
        ),
        "regra": _regra_teste,
    }

    return CapabilityImplementation(
        definition=definicao,
        handler=avaliar_sweep001,
        acceptance_tests=[
            AcceptanceTest(
                name="rotacao-nao-inicializada-dispara",
                entrada=entrada_sucesso,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: len(saida["achados"]) == 1,
            ),
            AcceptanceTest(
                name="rotacao-dentro-da-cadencia-nao-dispara",
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
                    "caminho": "Batman/config/sweep_state.json",
                    "conteudo": "x",
                    "regra": {"severidade": 123},
                },
                resultado_esperado=ResultadoEsperado.TIMEOUT,
            ),
        ],
    )
