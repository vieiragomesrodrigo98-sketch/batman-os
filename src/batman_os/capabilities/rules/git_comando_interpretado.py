"""Skill "comando git único interpretado" (Vol.IV Cap.17) — Milestone 3,
Skill 3.

Cobre QA-008 (`UnpushedCommits`): roda UM comando git fixo (`git rev-list
--count @{u}..HEAD`), interpreta a saída como inteiro e dispara achado se
maior que um limiar. Handler continua puro: quem roda o `subprocess` é
`cli/descoberta_arquivos.py` (tipo de descoberta `"git"`) — mesmo padrão de
`regex_sobre_conteudo.py`, que nunca toca disco/processo.

`conteudo` chega como a saída do `git` já capturada (`stdout.strip()`,
`""` se o comando falhar/der timeout — replica `RepoContext.git()`:
`except Exception: return ""`, nunca propaga a falha como erro)."""

from __future__ import annotations

import hashlib
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


class RegraComparacaoNumericaSpec(BaseModel):
    codigo: str
    agente: str
    severidade: str
    categoria: str
    titulo: str
    causa: str
    remediacao: str
    limiar: int = 0


class EntradaGitInterpretado(BaseModel):
    tipo: Literal["git-interpretado"] = "git-interpretado"
    caminho: str
    conteudo: str | None = None
    regra: RegraComparacaoNumericaSpec


class AchadoGitInterpretado(BaseModel):
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


class SaidaGitInterpretado(BaseModel):
    achados: list[AchadoGitInterpretado] = Field(default_factory=list)


class EntradaInvalida(Exception):
    """Levantada quando `entrada` não satisfaz `EntradaGitInterpretado` —
    vira SCHEMA_REJECTION no Execution Engine (Vol.III Cap.12)."""


def _computar_fingerprint(agente: str, categoria: str, caminho: str, codigo: str) -> str:
    normalizado = caminho.replace("\\", "/")
    bruto = f"{agente}|{categoria}|{normalizado}|{codigo}|"
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()


def avaliar_regra_git_interpretado(entrada: Any, contexto: ExecutionContext) -> Any:
    del contexto
    try:
        dados = EntradaGitInterpretado.model_validate(entrada)
    except Exception as exc:
        raise EntradaInvalida(str(exc)) from exc

    conteudo = dados.conteudo or ""
    if not (conteudo.isdigit() and int(conteudo) > dados.regra.limiar):
        return SaidaGitInterpretado(achados=[]).model_dump()

    regra = dados.regra
    fingerprint = _computar_fingerprint(regra.agente, regra.categoria, dados.caminho, regra.codigo)
    achado = AchadoGitInterpretado(
        codigo=regra.codigo,
        agente=regra.agente,
        severidade=regra.severidade,
        categoria=regra.categoria,
        titulo=regra.titulo,
        descricao=f"{dados.caminho}: {regra.titulo} ({conteudo}).",
        causa=regra.causa,
        remediacao=regra.remediacao,
        arquivo=dados.caminho,
        fingerprint=fingerprint,
    )
    return SaidaGitInterpretado(achados=[achado]).model_dump()


def construir_implementacao() -> CapabilityImplementation:
    definicao = CapabilityDefinition(
        id=CapabilityId("git-comando-interpretado"),
        name="Git: comando unico interpretado (comparacao numerica)",
        version="1.0.0",
        input_schema=EntradaGitInterpretado.model_json_schema(),
        output_schema=SaidaGitInterpretado.model_json_schema(),
        deterministic=True,
        side_effects=SideEffects.NONE,
        idempotent=True,
    )

    regra_teste = {
        "codigo": "TEST-GIT-001",
        "agente": "teste",
        "severidade": "medium",
        "categoria": "teste",
        "titulo": "teste",
        "causa": "teste",
        "remediacao": "teste",
        "limiar": 0,
    }
    entrada_sucesso = {"caminho": ".git", "conteudo": "3", "regra": regra_teste}
    entrada_conteudo_vazio = {"caminho": ".git", "conteudo": "", "regra": regra_teste}
    entrada_regra_invalida = {
        "caminho": ".git",
        "conteudo": "3",
        "regra": {**regra_teste, "limiar": "nao-e-um-inteiro"},
    }

    return CapabilityImplementation(
        definition=definicao,
        handler=avaliar_regra_git_interpretado,
        acceptance_tests=[
            AcceptanceTest(
                name="numero-acima-do-limiar-dispara",
                entrada=entrada_sucesso,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: len(saida["achados"]) == 1,
            ),
            AcceptanceTest(
                name="entrada-sem-campo-obrigatorio-e-rejeitada",
                entrada={"caminho": ".git"},
                resultado_esperado=ResultadoEsperado.SCHEMA_REJECTION,
            ),
            AcceptanceTest(
                name="conteudo_vazio_nao_dispara",
                entrada=entrada_conteudo_vazio,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: saida["achados"] == [],
            ),
            AcceptanceTest(
                name="regra-com-tipo-de-campo-invalido-e-tratada-como-falha-de-invocacao",
                entrada=entrada_regra_invalida,
                resultado_esperado=ResultadoEsperado.TIMEOUT,
            ),
        ],
    )
