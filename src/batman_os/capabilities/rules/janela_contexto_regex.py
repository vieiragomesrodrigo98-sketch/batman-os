"""Skill "janela de contexto por ocorrência" (Vol.IV Cap.17).

Generaliza o padrão que se repete em ~6 códigos da continuação da migração
(A11Y-005, A11Y-009, CRO-004, EH-009, IR-005 nesta primeira leva): para cada
LINHA que casa `pattern_trigger`, o legado extrai uma janela de N linhas
antes/depois e decide se a ocorrência é segura examinando essa janela — não
o arquivo inteiro (que é o que `ast_padrao_ausente`/`regex_agregado` cobrem).

Achado agrega TODAS as linhas sinalizadas de um arquivo num único achado
(`fmt_lines`-equivalente) — replica o padrão já visto em `regex_sobre_
conteudo`/`ast_padrao_ausente`: legado às vezes `yield`a por ocorrência
(EH-009, IR-005 dentro do loop) e às vezes agrega numa lista antes de um
único `yield` (A11Y-005, A11Y-009) — mas como nenhum desses achados define
`chave`, todas as ocorrências da MESMA regra no MESMO arquivo colapsam no
MESMO fingerprint (chave vazia) independente de quantos `yield`s o legado
faz — um único achado agregado é equivalente para fins de comparação.

Dois mecanismos de "essa ocorrência é segura" (mutuamente combináveis):
- `pattern_mitigacao`: se a JANELA casa esse padrão, a ocorrência é segura
  (replica A11Y-005 `_FOCUS_RING`, A11Y-009 "autocomplete", EH-009 "'exp'"/
  '"exp"', IR-005 `_ROTATION` — presença de proteção na vizinhança).
- `pattern_risco`: se a JANELA **não** casa esse padrão, a ocorrência é segura
  — inverso de `pattern_mitigacao`: exige que um padrão de RISCO também
  esteja presente na janela para disparar (replica CRO-004: só marca
  `type="text"` se o contexto também menciona email/phone/cpf).

`pattern_gate_arquivo` (opcional): pré-condição sobre o arquivo INTEIRO,
antes de processar qualquer linha — combinável via `\\A(?=X)(?=Y)` para
"E" de duas condições (replica o gate duplo de CRO-004: só processa
arquivos que têm AMBOS email/phone E type="text" em algum lugar)."""

from __future__ import annotations

import hashlib
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


class RegraJanelaSpec(BaseModel):
    codigo: str
    agente: str
    severidade: str
    categoria: str
    titulo: str
    causa: str
    remediacao: str
    pattern_trigger: str
    pattern_gate_arquivo: str | None = None
    pattern_mitigacao: str | None = None
    pattern_risco: str | None = None
    janela_antes: int = 0
    janela_depois: int = 0
    ignore_case: bool = False


class EntradaJanela(BaseModel):
    """`tipo` é o mesmo discriminador estrutural das outras Entradas desta
    migração (ver nota em `EntradaAgregada`)."""

    tipo: Literal["janela-contexto"] = "janela-contexto"
    caminho: str
    conteudo: str | None = None
    regra: RegraJanelaSpec


class AchadoJanela(BaseModel):
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


class SaidaJanela(BaseModel):
    achados: list[AchadoJanela] = Field(default_factory=list)


class EntradaInvalida(Exception):
    """Levantada quando `entrada` não satisfaz `EntradaJanela` — vira
    SCHEMA_REJECTION no Execution Engine (Vol.III Cap.12)."""


def _computar_fingerprint(agente: str, categoria: str, caminho: str, codigo: str) -> str:
    normalizado = caminho.replace("\\", "/")
    bruto = f"{agente}|{categoria}|{normalizado}|{codigo}|"
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()


def _fmt_lines(linhas: list[int]) -> str:
    return ",".join(str(n) for n in linhas)


def avaliar_regra_janela(entrada: Any, contexto: ExecutionContext) -> Any:
    del contexto
    try:
        dados = EntradaJanela.model_validate(entrada)
    except Exception as exc:
        raise EntradaInvalida(str(exc)) from exc

    regra = dados.regra
    texto = dados.conteudo or ""
    flags = re.IGNORECASE if regra.ignore_case else 0

    if regra.pattern_gate_arquivo and not re.search(regra.pattern_gate_arquivo, texto, flags):
        return SaidaJanela(achados=[]).model_dump()

    linhas = texto.splitlines()
    sinalizadas: list[int] = []
    for i, linha in enumerate(linhas):
        if not re.search(regra.pattern_trigger, linha, flags):
            continue
        inicio = max(0, i - regra.janela_antes)
        fim = i + regra.janela_depois + 1
        janela = "\n".join(linhas[inicio:fim])
        if regra.pattern_mitigacao and re.search(regra.pattern_mitigacao, janela, flags):
            continue
        if regra.pattern_risco and not re.search(regra.pattern_risco, janela, flags):
            continue
        sinalizadas.append(i + 1)

    if not sinalizadas:
        return SaidaJanela(achados=[]).model_dump()

    fingerprint = _computar_fingerprint(regra.agente, regra.categoria, dados.caminho, regra.codigo)
    achado = AchadoJanela(
        codigo=regra.codigo,
        agente=regra.agente,
        severidade=regra.severidade,
        categoria=regra.categoria,
        titulo=regra.titulo,
        descricao=f"{dados.caminho}: {regra.titulo} (linhas {_fmt_lines(sinalizadas)}).",
        causa=regra.causa,
        remediacao=regra.remediacao,
        arquivo=dados.caminho,
        fingerprint=fingerprint,
    )
    return SaidaJanela(achados=[achado]).model_dump()


def construir_implementacao() -> CapabilityImplementation:
    definicao = CapabilityDefinition(
        id=CapabilityId("janela-contexto-regex"),
        name="Janela de contexto por ocorrencia",
        version="1.0.0",
        input_schema=EntradaJanela.model_json_schema(),
        output_schema=SaidaJanela.model_json_schema(),
        deterministic=True,
        side_effects=SideEffects.NONE,
        idempotent=True,
    )

    entrada_sucesso = {
        "caminho": "a.tsx",
        "conteudo": "trigger aqui\nlinha sem mitigacao\n",
        "regra": {
            "codigo": "TEST-JAN-001",
            "agente": "teste",
            "severidade": "high",
            "categoria": "teste",
            "titulo": "teste",
            "causa": "teste",
            "remediacao": "teste",
            "pattern_trigger": "trigger",
            "pattern_mitigacao": "mitigacao-que-nao-existe-aqui",
            "janela_antes": 0,
            "janela_depois": 1,
        },
    }
    entrada_regex_malformado = {
        "caminho": "a.tsx",
        "conteudo": "x",
        "regra": {
            "codigo": "TEST-JAN-002",
            "agente": "teste",
            "severidade": "high",
            "categoria": "teste",
            "titulo": "teste",
            "causa": "teste",
            "remediacao": "teste",
            "pattern_trigger": "(",
            "janela_antes": 0,
            "janela_depois": 0,
        },
    }

    return CapabilityImplementation(
        definition=definicao,
        handler=avaliar_regra_janela,
        acceptance_tests=[
            AcceptanceTest(
                name="trigger-sem-mitigacao-na-janela-dispara-um-achado",
                entrada=entrada_sucesso,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: len(saida["achados"]) == 1,
            ),
            AcceptanceTest(
                name="entrada-sem-campo-obrigatorio-e-rejeitada",
                entrada={"caminho": "a.tsx"},  # falta 'regra'
                resultado_esperado=ResultadoEsperado.SCHEMA_REJECTION,
            ),
            AcceptanceTest(
                name="pattern-malformado-e-tratado-como-falha-de-invocacao",
                entrada=entrada_regex_malformado,
                resultado_esperado=ResultadoEsperado.TIMEOUT,
            ),
        ],
    )
