"""Capability bespoke — ORA-004 (Vol.IV Cap.17) — Milestone 3, Skill 6.

Replica `Batman/scan/rules/oracle.py::StatusLiteralTypo`: acha literais de
status (`status = "x"`, `status: "x"`, SQL cru `WHERE status = 'x'`) cujo
valor diverge por 1 caractere de um valor dominante no mesmo domínio
(classe de bug C7, auditoria jul/2026 — `/metrics/advanced` e
`/retrospectiva` mortos porque filtravam `status='fechada'` quando o
canônico era `'fechado'`).

Diferente das demais Capabilities desta migração: a frequência (para achar
o "dominante") é contada ATRAVÉS DE TODOS OS ARQUIVOS do repo, não por
arquivo — não generalizado em Skill (agregação repo-inteira + comparação
por distância-1 não se repete em nenhuma outra regra migrada)."""

from __future__ import annotations

import ast
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

AGENTE = "oracle"
CATEGORIA = "consistencia-schema"
CODIGO = "ORA-004"

_SQL_STATUS_RX = re.compile(r"status\s*=?=\s*['\"]([a-z_][a-z0-9_]*)['\"]", re.IGNORECASE)
_SQL_IN_RX = re.compile(r"status\s+IN\s*\(([^)]*)\)", re.IGNORECASE)
_QUOTED_RX = re.compile(r"['\"]([a-z_][a-z0-9_]*)['\"]")
_WORD_RX = re.compile(r"[a-z][a-z0-9_]{3,}")


class RegraOra004Spec(BaseModel):
    codigo: str = CODIGO
    agente: str = AGENTE
    severidade: str = "high"
    categoria: str = CATEGORIA
    titulo: str = "Literal de status diverge do vocabulário dominante — typo provável"
    causa: str = (
        "A classe de bug C7 (auditoria jul/2026): /metrics/advanced e /retrospectiva "
        "ficaram mortos porque filtravam status='fechada' enquanto o valor canônico é "
        "'fechado'. A query nunca casa, o endpoint responde 'sem dados' e ninguém "
        "percebe. Um literal raro a 1 caractere de um literal dominante no mesmo "
        "domínio é typo até prova em contrário."
    )
    remediacao: str = (
        "Corrija o literal para o valor dominante/canônico, ou — se o valor raro for "
        "legítimo — promova o vocabulário para um Enum em src/radar/models/enums.py e "
        "use o Enum nos dois lados. DoD: grep do literal errado zerado + teste "
        "exercitando o filtro."
    )


class EntradaOra004(BaseModel):
    tipo: Literal["ora004"] = "ora004"
    caminho: str
    conteudo: str | None = None
    regra: RegraOra004Spec = Field(default_factory=RegraOra004Spec)


class AchadoOra004(BaseModel):
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


class SaidaOra004(BaseModel):
    achados: list[AchadoOra004] = Field(default_factory=list)


class EntradaInvalida(Exception):
    """Levantada quando `entrada` não satisfaz `EntradaOra004` — vira
    SCHEMA_REJECTION no Execution Engine (Vol.III Cap.12)."""


class _Payload(BaseModel):
    arquivos: dict[str, str] = Field(default_factory=dict)
    enums_src: str | None = None


def _computar_fingerprint(caminho: str, chave: str) -> str:
    normalizado = caminho.replace("\\", "/")
    bruto = f"{AGENTE}|{CATEGORIA}|{normalizado}|{CODIGO}|{chave}"
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()


def _is_status_name(name: str) -> bool:
    n = name.lower()
    return n.endswith("status") and "http" not in n


def _is_status_ref(node: ast.AST) -> bool:
    if isinstance(node, ast.Attribute):
        return _is_status_name(node.attr)
    if isinstance(node, ast.Name):
        return _is_status_name(node.id)
    if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
        return isinstance(node.slice.value, str) and _is_status_name(node.slice.value)
    return False


def _sql_status_values(text: str) -> list[str]:
    vals = [m.group(1) for m in _SQL_STATUS_RX.finditer(text)]
    for m in _SQL_IN_RX.finditer(text):
        vals.extend(q.group(1) for q in _QUOTED_RX.finditer(m.group(1)))
    return vals


def _status_literals(tree: ast.AST) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and len(node.comparators) == 1:
            left, right = node.left, node.comparators[0]
            for tgt, lit in ((left, right), (right, left)):
                if (
                    _is_status_ref(tgt)
                    and isinstance(lit, ast.Constant)
                    and isinstance(lit.value, str)
                ):
                    out.append((lit.lineno, lit.value))
        elif isinstance(node, ast.Call):
            for kw in node.keywords:
                if (
                    kw.arg
                    and _is_status_name(kw.arg)
                    and isinstance(kw.value, ast.Constant)
                    and isinstance(kw.value.value, str)
                ):
                    out.append((kw.value.lineno, kw.value.value))
        elif isinstance(node, ast.Assign):
            if (
                isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
                and any(_is_status_ref(t) for t in node.targets)
            ):
                out.append((node.value.lineno, node.value.value))
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and len(node.value) > 20
            and "status" in node.value.lower()
        ):
            out.extend((node.lineno, v) for v in _sql_status_values(node.value))
    return out


def _one_char_apart(a: str, b: str) -> bool:
    if len(a) != len(b) or a == b:
        return False
    return sum(1 for x, y in zip(a, b, strict=False) if x != y) == 1


def _enum_values(enums_src: str | None) -> set[str]:
    if not enums_src:
        return set()
    try:
        tree = ast.parse(enums_src)
    except SyntaxError:
        return set()
    vals: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for st in node.body:
                if (
                    isinstance(st, ast.Assign)
                    and isinstance(st.value, ast.Constant)
                    and isinstance(st.value.value, str)
                ):
                    vals.add(st.value.value)
    return vals


def _detectar(regra: RegraOra004Spec, payload: _Payload) -> list[AchadoOra004]:
    ocorrencias: dict[str, list[tuple[str, int]]] = {}
    for rel, source in sorted(payload.arquivos.items()):
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for lineno, value in _status_literals(tree):
            v = value.strip().lower()
            if _WORD_RX.fullmatch(v):
                ocorrencias.setdefault(v, []).append((rel, lineno))

    if not ocorrencias:
        return []

    canonical = _enum_values(payload.enums_src)
    counts = {v: len(occ) for v, occ in ocorrencias.items()}

    achados: list[AchadoOra004] = []
    for v, occ in sorted(ocorrencias.items()):
        if v in canonical:
            continue
        dominant: str | None = None
        for w, cw in counts.items():
            if _one_char_apart(v, w) and cw >= 3 and cw >= 3 * counts[v]:
                dominant = f"'{w}' ({cw} usos)"
                break
        if dominant is None and counts[v] <= 2:
            for w in canonical:
                if _one_char_apart(v, w):
                    dominant = f"'{w}' (Enum canônico)"
                    break
        if dominant is None:
            continue

        por_arquivo: dict[str, list[int]] = {}
        for rel, lineno in occ:
            por_arquivo.setdefault(rel, []).append(lineno)
        for rel, linhas in sorted(por_arquivo.items()):
            ls = ",".join(str(x) for x in sorted(linhas))
            descricao = f"{rel}: status '{v}' (linha(s) {ls}) diverge de {dominant} — typo provável"
            achados.append(
                AchadoOra004(
                    codigo=regra.codigo,
                    agente=regra.agente,
                    severidade=regra.severidade,
                    categoria=regra.categoria,
                    titulo=regra.titulo,
                    descricao=descricao,
                    causa=regra.causa,
                    remediacao=regra.remediacao,
                    arquivo=rel,
                    chave=v,
                    fingerprint=_computar_fingerprint(rel, v),
                )
            )
    return achados


def avaliar_ora004(entrada: Any, contexto: ExecutionContext) -> Any:
    del contexto
    try:
        dados = EntradaOra004.model_validate(entrada)
    except Exception as exc:
        raise EntradaInvalida(str(exc)) from exc

    if dados.conteudo is None:
        return SaidaOra004(achados=[]).model_dump()

    try:
        import json

        payload = _Payload.model_validate(json.loads(dados.conteudo))
    except Exception:
        return SaidaOra004(achados=[]).model_dump()

    achados = _detectar(dados.regra, payload)
    return SaidaOra004(achados=achados).model_dump()


def construir_implementacao() -> CapabilityImplementation:
    definicao = CapabilityDefinition(
        id=CapabilityId("ora004-status-typo"),
        name="ORA-004: literal de status diverge do vocabulario dominante",
        version="1.0.0",
        input_schema=EntradaOra004.model_json_schema(),
        output_schema=SaidaOra004.model_json_schema(),
        deterministic=True,
        side_effects=SideEffects.NONE,
        idempotent=True,
    )

    import json

    arquivos_dispara = {
        "src/a.py": "\n".join([f"x = status == 'fechado'  # {i}" for i in range(4)]),
        "src/b.py": "y = status == 'fechada'",
    }
    entrada_sucesso = {
        "caminho": "src",
        "conteudo": json.dumps({"arquivos": arquivos_dispara, "enums_src": None}),
        "regra": {},
    }
    entrada_vazia = {
        "caminho": "src",
        "conteudo": json.dumps({"arquivos": {}, "enums_src": None}),
        "regra": {},
    }
    entrada_conteudo_malformado = {"caminho": "src", "conteudo": "nao e json", "regra": {}}
    entrada_regra_invalida = {
        "caminho": "src",
        "conteudo": json.dumps({"arquivos": {}, "enums_src": None}),
        "regra": {"severidade": 123},
    }

    return CapabilityImplementation(
        definition=definicao,
        handler=avaliar_ora004,
        acceptance_tests=[
            AcceptanceTest(
                name="literal-raro-diverge-do-dominante-dispara",
                entrada=entrada_sucesso,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: len(saida["achados"]) == 1,
            ),
            AcceptanceTest(
                name="sem-arquivos-retorna-vazio",
                entrada=entrada_vazia,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: saida["achados"] == [],
            ),
            AcceptanceTest(
                name="entrada-sem-campo-obrigatorio-e-rejeitada",
                entrada={"conteudo": "x"},
                resultado_esperado=ResultadoEsperado.SCHEMA_REJECTION,
            ),
            AcceptanceTest(
                name="conteudo-malformado-nao-quebra-o-handler",
                entrada=entrada_conteudo_malformado,
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
