"""Capability bespoke FE-002 ".toFixed() sem optional chaining — risco de
TypeError em valor nulo" (Vol.IV Cap.17).

Não generalizada em Skill — lookback de até 15 linhas CIENTE DO RECEPTOR
(verifica se o guard na linha anterior menciona a MESMA variável/
expressão que recebe `.toFixed()`, não qualquer guard genérico) — lógica
de múltiplos passos (extrai receptores da linha, sanitiza padrões
seguros inline, verifica guards na própria linha, depois olha pra trás
CONDICIONADO ao receptor) que não é expressável como regex único nem
como janela fixa em torno de uma âncora."""

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

_SAFE_INLINE = re.compile(r"\?\s*\.toFixed\(" r"|(\?\?\s*0|\|\|\s*0)\s*\)\.toFixed\(")
_NULL_COALESCE_ZERO = re.compile(r"\?\?\s*0")
_LOGICAL_OR_ZERO = re.compile(r"\|\|\s*0")
_NULL_GUARD = re.compile(r"!==?\s*null|null\s*!==?|\bnull\s*&&|\bnull\b.*\?|>\s*0\s*[?&]")
_GUARD_TOKENS = re.compile(r"[!=]==?\s*null|null\s*[!=]==?|>\s*0|Number\.isFinite|isFinite\(")
_LOOKBACK_LINES = 15

_ADMIN_COMPONENTS: frozenset[str] = frozenset(
    {
        "MotorAdmin.tsx",
        "FinanceiroAdmin.tsx",
        "Observabilidade.tsx",
        "PlanosCRUD.tsx",
        "TesteCarga.tsx",
    }
)


class RegraFe002Spec(BaseModel):
    codigo: str
    agente: str
    severidade: str
    categoria: str
    titulo: str
    causa: str
    remediacao: str


class EntradaFe002(BaseModel):
    tipo: Literal["fe002"] = "fe002"
    caminho: str
    conteudo: str | None = None
    regra: RegraFe002Spec


class AchadoFe002(BaseModel):
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


class SaidaFe002(BaseModel):
    achados: list[AchadoFe002] = Field(default_factory=list)


class EntradaInvalida(Exception):
    """Levantada quando `entrada` não satisfaz `EntradaFe002` — vira
    SCHEMA_REJECTION no Execution Engine (Vol.III Cap.12)."""


def _computar_fingerprint(agente: str, categoria: str, caminho: str, codigo: str) -> str:
    import hashlib

    normalizado = caminho.replace("\\", "/")
    bruto = f"{agente}|{categoria}|{normalizado}|{codigo}|"
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()


def _fmt_lines(lines: list[int]) -> str:
    return ",".join(str(x) for x in sorted(set(lines)))


def _receivers(line: str) -> set[str]:
    """Expressões (e suas raízes) sobre as quais .toFixed() é chamado na
    linha."""
    out: set[str] = set()
    for m in re.finditer(r"([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\.toFixed\(", line):
        expr = m.group(1)
        out.add(expr)
        out.add(expr.split(".")[0])
    for m in re.finditer(r"Number\(([^()]*)\)\.toFixed\(", line):
        inner = m.group(1).strip()
        if inner:
            out.add(inner)
            root = re.match(r"[A-Za-z_$][\w$]*", inner)
            if root:
                out.add(root.group(0))
    return {o for o in out if o and o not in ("Number", "Math")}


def _guarded_above(lines: list[str], idx: int, receivers: set[str]) -> bool:
    """True se alguma das `_LOOKBACK_LINES` anteriores guarda um dos
    receptores."""
    start = max(0, idx - 1 - _LOOKBACK_LINES)
    for prev in lines[start : idx - 1]:
        for r in receivers:
            mention = re.search(rf"(?<![\w$.]){re.escape(r)}(?![\w$])", prev)
            if not mention:
                continue
            if _GUARD_TOKENS.search(prev):
                return True
            if re.search(rf"(?<![\w$.]){re.escape(r)}(?![\w$])\s*&&", prev):
                return True
    return False


def _linhas_arriscadas(text: str) -> list[int]:
    all_lines = text.splitlines()
    risky: list[int] = []
    for i, line in enumerate(all_lines, 1):
        if not re.search(r"\.toFixed\(", line):
            continue
        sanitized = _SAFE_INLINE.sub("", line)
        if not re.search(r"(?<!\?)\.toFixed\(", sanitized):
            continue
        if _NULL_COALESCE_ZERO.search(line) or _LOGICAL_OR_ZERO.search(line):
            continue
        if _NULL_GUARD.search(line):
            continue
        if _guarded_above(all_lines, i, _receivers(line)):
            continue
        risky.append(i)
    return risky


def avaliar_fe002(entrada: Any, contexto: ExecutionContext) -> Any:
    del contexto
    try:
        dados = EntradaFe002.model_validate(entrada)
    except Exception as exc:
        raise EntradaInvalida(str(exc)) from exc

    caminho_normalizado = dados.caminho.replace("\\", "/")
    if not caminho_normalizado.endswith(".tsx"):
        return SaidaFe002(achados=[]).model_dump()
    nome_arquivo = caminho_normalizado.rsplit("/", 1)[-1]
    if nome_arquivo in _ADMIN_COMPONENTS:
        return SaidaFe002(achados=[]).model_dump()
    if ".test." in caminho_normalizado or ".spec." in caminho_normalizado:
        return SaidaFe002(achados=[]).model_dump()

    if dados.conteudo is None:
        return SaidaFe002(achados=[]).model_dump()

    risky = _linhas_arriscadas(dados.conteudo)
    if not risky:
        return SaidaFe002(achados=[]).model_dump()

    regra = dados.regra
    fingerprint = _computar_fingerprint(regra.agente, regra.categoria, dados.caminho, regra.codigo)
    achado = AchadoFe002(
        codigo=regra.codigo,
        agente=regra.agente,
        severidade=regra.severidade,
        categoria=regra.categoria,
        titulo=regra.titulo,
        descricao=(
            f"{dados.caminho}: .toFixed() sem optional chaining (linhas {_fmt_lines(risky)})."
        ),
        causa=regra.causa,
        remediacao=regra.remediacao,
        arquivo=dados.caminho,
        fingerprint=fingerprint,
    )
    return SaidaFe002(achados=[achado]).model_dump()


def construir_implementacao() -> CapabilityImplementation:
    definicao = CapabilityDefinition(
        id=CapabilityId("fe002-tofixed-sem-null-safety"),
        name="FE-002 toFixed sem optional chaining",
        version="1.0.0",
        input_schema=EntradaFe002.model_json_schema(),
        output_schema=SaidaFe002.model_json_schema(),
        deterministic=True,
        side_effects=SideEffects.NONE,
        idempotent=True,
    )

    _regra_teste = {
        "codigo": "FE-002",
        "agente": "frontend-engineer",
        "severidade": "medium",
        "categoria": "robustez",
        "titulo": "t",
        "causa": "c",
        "remediacao": "r",
    }
    entrada_sucesso = {
        "caminho": "frontend/src/Card.tsx",
        "conteudo": "const x = valor.toFixed(2);\n",
        "regra": _regra_teste,
    }
    entrada_ok = {
        "caminho": "frontend/src/Card.tsx",
        "conteudo": "const x = valor?.toFixed(2);\n",
        "regra": _regra_teste,
    }

    return CapabilityImplementation(
        definition=definicao,
        handler=avaliar_fe002,
        acceptance_tests=[
            AcceptanceTest(
                name="tofixed-sem-null-safety-dispara",
                entrada=entrada_sucesso,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: len(saida["achados"]) == 1,
            ),
            AcceptanceTest(
                name="tofixed-com-optional-chaining-nao-dispara",
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
                    "caminho": "frontend/src/x.tsx",
                    "conteudo": "x",
                    "regra": {"severidade": 123},
                },
                resultado_esperado=ResultadoEsperado.TIMEOUT,
            ),
        ],
    )
