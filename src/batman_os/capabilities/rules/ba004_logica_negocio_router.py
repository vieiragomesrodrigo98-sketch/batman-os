"""Capability bespoke BA-004 "lógica de negócio no router" (Vol.IV Cap.17).

Não generalizada numa Skill — combinação única: gate de arquivo inteiro
(ausência de `service.`/`repo.`/import de `.services`), seletor de
FunctionDef POR DECORATOR restrito a rotas HTTP (`@router.get/post/put/
patch/delete`), contagem de operações aritméticas (`BinOp` com Mult/Div/
Mod) SÓ dentro dessas funções-rota, excluindo divisão estilo `Path`
(`caminho / "str"` — right operand `Constant`/`JoinedStr`), com limiar de
3 linhas distintas. Diferente de `metrica_com_limiar` (que conta métricas
uniformes por arquivo/função, não filtra por tipo de nó BinOp com exceção
estrutural) e de `ast_padrao_ausente` (seleciona por corpo/contexto via
regex, não por contagem de sub-nós de um tipo específico)."""

from __future__ import annotations

import ast
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

_SERVICE_RE = re.compile(r"service\.|repo\.|from\s+api\.services|from\s+\w+\.services")
_MIN_ARITH_LINES = 3
_METODOS_ROTA = ("get", "post", "put", "patch", "delete")


class RegraBa004Spec(BaseModel):
    codigo: str
    agente: str
    severidade: str
    categoria: str
    titulo: str
    causa: str
    remediacao: str


class EntradaBa004(BaseModel):
    tipo: Literal["ba004"] = "ba004"
    caminho: str
    conteudo: str | None = None
    regra: RegraBa004Spec


class AchadoBa004(BaseModel):
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


class SaidaBa004(BaseModel):
    achados: list[AchadoBa004] = Field(default_factory=list)


class EntradaInvalida(Exception):
    """Levantada quando `entrada` não satisfaz `EntradaBa004` — vira
    SCHEMA_REJECTION no Execution Engine (Vol.III Cap.12)."""


def _computar_fingerprint(agente: str, categoria: str, caminho: str, codigo: str) -> str:
    import hashlib

    normalizado = caminho.replace("\\", "/")
    bruto = f"{agente}|{categoria}|{normalizado}|{codigo}|"
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()


def _e_rota_http(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(
        isinstance(d, ast.Call)
        and isinstance(d.func, ast.Attribute)
        and d.func.attr in _METODOS_ROTA
        for d in node.decorator_list
    )


def _linhas_aritmeticas(tree: ast.Module) -> list[int]:
    arith_lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or not _e_rota_http(node):
            continue
        for child in ast.walk(node):
            if not (
                isinstance(child, ast.BinOp) and isinstance(child.op, (ast.Mult, ast.Div, ast.Mod))
            ):
                continue
            if isinstance(child.op, ast.Div) and isinstance(
                child.right, (ast.Constant, ast.JoinedStr)
            ):
                continue
            lineno = getattr(child, "lineno", None)
            if lineno and lineno not in arith_lines:
                arith_lines.append(lineno)
    return arith_lines


def avaliar_ba004(entrada: Any, contexto: ExecutionContext) -> Any:
    del contexto
    try:
        dados = EntradaBa004.model_validate(entrada)
    except Exception as exc:
        raise EntradaInvalida(str(exc)) from exc

    texto = dados.conteudo or ""
    if _SERVICE_RE.search(texto):
        return SaidaBa004(achados=[]).model_dump()

    try:
        tree = ast.parse(texto)
    except SyntaxError:
        return SaidaBa004(achados=[]).model_dump()

    arith_lines = _linhas_aritmeticas(tree)
    if len(arith_lines) < _MIN_ARITH_LINES:
        return SaidaBa004(achados=[]).model_dump()

    regra = dados.regra
    fingerprint = _computar_fingerprint(regra.agente, regra.categoria, dados.caminho, regra.codigo)
    linhas = ",".join(str(n) for n in sorted(arith_lines))
    achado = AchadoBa004(
        codigo=regra.codigo,
        agente=regra.agente,
        severidade=regra.severidade,
        categoria=regra.categoria,
        titulo=regra.titulo,
        descricao=(
            f"{dados.caminho}: possível lógica de negócio no router sem camada de "
            f"serviço (linhas {linhas})."
        ),
        causa=regra.causa,
        remediacao=regra.remediacao,
        arquivo=dados.caminho,
        fingerprint=fingerprint,
    )
    return SaidaBa004(achados=[achado]).model_dump()


def construir_implementacao() -> CapabilityImplementation:
    definicao = CapabilityDefinition(
        id=CapabilityId("ba004-logica-negocio-router"),
        name="BA-004 logica de negocio no router",
        version="1.0.0",
        input_schema=EntradaBa004.model_json_schema(),
        output_schema=SaidaBa004.model_json_schema(),
        deterministic=True,
        side_effects=SideEffects.NONE,
        idempotent=True,
    )

    _regra_teste = {
        "codigo": "BA-004",
        "agente": "business-analyst",
        "severidade": "medium",
        "categoria": "arquitetura",
        "titulo": "t",
        "causa": "c",
        "remediacao": "r",
    }
    entrada_sucesso = {
        "caminho": "api/routers/x.py",
        "conteudo": (
            "@router.get('/calc')\n"
            "def calc(a: int, b: int, c: int):\n"
            "    x = a * b\n"
            "    y = b / c\n"
            "    z = a % c\n"
            "    return x + y + z\n"
        ),
        "regra": _regra_teste,
    }
    entrada_ok_com_service = {
        "caminho": "api/routers/y.py",
        "conteudo": (
            "@router.get('/calc')\n"
            "def calc(a: int, b: int, c: int):\n"
            "    return service.compute(a, b, c)\n"
        ),
        "regra": _regra_teste,
    }

    return CapabilityImplementation(
        definition=definicao,
        handler=avaliar_ba004,
        acceptance_tests=[
            AcceptanceTest(
                name="rota-com-3-operacoes-aritmeticas-dispara-um-achado",
                entrada=entrada_sucesso,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: len(saida["achados"]) == 1,
            ),
            AcceptanceTest(
                name="arquivo-com-camada-de-servico-nao-dispara",
                entrada=entrada_ok_com_service,
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
                entrada={"caminho": "a.py", "conteudo": "x", "regra": {"severidade": 123}},
                resultado_esperado=ResultadoEsperado.TIMEOUT,
            ),
        ],
    )
