"""Capability bespoke BA-005 "divisão sem guarda contra zero" (Vol.IV
Cap.17).

Não generalizada numa Skill — três mecanismos que não se repetem juntos
em nenhum outro código: (1) filtro de ARQUIVO por PALAVRA-CHAVE NO
CAMINHO (`financial`/`trading`/`portfolio`/`risk`/`signal`/`engine`,
case-insensitive) — filtro de INCLUSÃO, não exclusão (a descoberta
`"arvore"` só suporta exclusão; aqui o filtro roda dentro do próprio
handler, sobre `dados.caminho`, sem precisar estender a camada de
descoberta); (2) máquina de estados rastreando docstring multi-linha
(`\"\"\"`/`'''`) para não falsamente disparar em divisão mencionada
dentro de texto de documentação; (3) gate de exceção sobre o arquivo
INTEIRO (`_GUARD_RE`) que suprime o achado mesmo com divisões
encontradas, se alguma forma de proteção contra zero existe em
QUALQUER lugar do arquivo."""

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

_PALAVRAS_CHAVE_CAMINHO = ("financial", "trading", "portfolio", "risk", "signal", "engine")
_DIV_RE = re.compile(r"\b\w{2,}\s*/\s*(?!\d)(?!/)(?!\*)\b\w{2,}")
_GUARD_RE = re.compile(
    r"ZeroDivisionError|!=\s*0|[<>]=?\s*0\b|if\s+\w[\w.]*\s+else\b"
    r"|\babs\(|\bor\s+0\b|\bor\s+1\b|/\s*_?[A-Z][A-Z0-9_]{2,}\b"
)
_SLASH_SLASH = re.compile(r"//")


class RegraBa005Spec(BaseModel):
    codigo: str
    agente: str
    severidade: str
    categoria: str
    titulo: str
    causa: str
    remediacao: str


class EntradaBa005(BaseModel):
    tipo: Literal["ba005"] = "ba005"
    caminho: str
    conteudo: str | None = None
    regra: RegraBa005Spec


class AchadoBa005(BaseModel):
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


class SaidaBa005(BaseModel):
    achados: list[AchadoBa005] = Field(default_factory=list)


class EntradaInvalida(Exception):
    """Levantada quando `entrada` não satisfaz `EntradaBa005` — vira
    SCHEMA_REJECTION no Execution Engine (Vol.III Cap.12)."""


def _computar_fingerprint(agente: str, categoria: str, caminho: str, codigo: str) -> str:
    import hashlib

    normalizado = caminho.replace("\\", "/")
    bruto = f"{agente}|{categoria}|{normalizado}|{codigo}|"
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()


def _linhas_com_divisao_sem_guarda(texto: str) -> list[int]:
    div_lines: list[int] = []
    in_docstring = False
    docstring_marker = ""
    for i, line in enumerate(texto.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if in_docstring:
            if docstring_marker in stripped:
                in_docstring = False
            continue
        if stripped.startswith(('"""', "'''")):
            marker = stripped[:3]
            rest = stripped[3:]
            if marker in rest:
                continue
            in_docstring = True
            docstring_marker = marker
            continue
        if stripped.startswith(("from ", "import ")):
            continue
        code_part = stripped.split(" # ")[0] if " # " in stripped else stripped
        if _DIV_RE.search(code_part) and not _SLASH_SLASH.search(code_part):
            div_lines.append(i)
    return div_lines


def avaliar_ba005(entrada: Any, contexto: ExecutionContext) -> Any:
    del contexto
    try:
        dados = EntradaBa005.model_validate(entrada)
    except Exception as exc:
        raise EntradaInvalida(str(exc)) from exc

    caminho_lower = dados.caminho.lower()
    if not any(kw in caminho_lower for kw in _PALAVRAS_CHAVE_CAMINHO):
        return SaidaBa005(achados=[]).model_dump()

    texto = dados.conteudo or ""
    div_lines = _linhas_com_divisao_sem_guarda(texto)
    if not div_lines or _GUARD_RE.search(texto):
        return SaidaBa005(achados=[]).model_dump()

    regra = dados.regra
    fingerprint = _computar_fingerprint(regra.agente, regra.categoria, dados.caminho, regra.codigo)
    linhas = ",".join(str(n) for n in div_lines)
    achado = AchadoBa005(
        codigo=regra.codigo,
        agente=regra.agente,
        severidade=regra.severidade,
        categoria=regra.categoria,
        titulo=regra.titulo,
        descricao=(
            f"{dados.caminho}: divisão sem guarda contra zero em módulo financeiro "
            f"(linhas {linhas})."
        ),
        causa=regra.causa,
        remediacao=regra.remediacao,
        arquivo=dados.caminho,
        fingerprint=fingerprint,
    )
    return SaidaBa005(achados=[achado]).model_dump()


def construir_implementacao() -> CapabilityImplementation:
    definicao = CapabilityDefinition(
        id=CapabilityId("ba005-divisao-sem-guarda"),
        name="BA-005 divisao sem guarda contra zero",
        version="1.0.0",
        input_schema=EntradaBa005.model_json_schema(),
        output_schema=SaidaBa005.model_json_schema(),
        deterministic=True,
        side_effects=SideEffects.NONE,
        idempotent=True,
    )

    _regra_teste = {
        "codigo": "BA-005",
        "agente": "business-analyst",
        "severidade": "high",
        "categoria": "financeiro",
        "titulo": "t",
        "causa": "c",
        "remediacao": "r",
    }
    entrada_sucesso = {
        "caminho": "src/radar/engines/risk_engine.py",
        "conteudo": "def calc(total, count):\n    return total / count\n",
        "regra": _regra_teste,
    }
    entrada_fora_do_escopo = {
        "caminho": "src/radar/utils/helpers.py",
        "conteudo": "def calc(total, count):\n    return total / count\n",
        "regra": _regra_teste,
    }

    return CapabilityImplementation(
        definition=definicao,
        handler=avaliar_ba005,
        acceptance_tests=[
            AcceptanceTest(
                name="divisao-sem-guarda-em-modulo-financeiro-dispara-um-achado",
                entrada=entrada_sucesso,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: len(saida["achados"]) == 1,
            ),
            AcceptanceTest(
                name="arquivo-fora-do-escopo-financeiro-nao-dispara",
                entrada=entrada_fora_do_escopo,
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
                    "caminho": "src/radar/engines/risk_engine.py",
                    "conteudo": "x",
                    "regra": {"severidade": 123},
                },
                resultado_esperado=ResultadoEsperado.TIMEOUT,
            ),
        ],
    )
