"""Capability bespoke BE-010 "dependência importada mas não declarada"
(Vol.IV Cap.17).

Não generalizada numa Skill — agregação GLOBAL com AGRUPAMENTO (mesmo
princípio de FE-001), mas a fonte de dados é TRIPLA: pyproject.toml (1
arquivo), lista de nomes de módulo local no ROOT do repo (não é conteúdo
de arquivo, é uma LISTAGEM de diretório), e TODOS os `.py` de `src_dirs`
(para extrair imports via AST). Constrói `seen: nome -> PRIMEIRO arquivo`
(ordem de `arquivos.items()`, que preserva a ordem de inserção da
descoberta — replica `seen.setdefault` do legado, que reporta o PRIMEIRO
arquivo encontrado). Para cada nome de import de terceiro (excluindo
stdlib, módulo local, prefixo `_`, e as dependências transitivas
conhecidas) ausente do texto de `pyproject.toml`, produz 1 achado com
`chave=nome`."""

from __future__ import annotations

import ast
import json
import sys
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

_STDLIB = set(getattr(sys, "stdlib_module_names", set()))
_KNOWN_TRANSITIVE = frozenset({"starlette"})


class RegraBe010Spec(BaseModel):
    codigo: str
    agente: str
    severidade: str
    categoria: str
    titulo: str
    causa: str
    remediacao: str


class EntradaBe010(BaseModel):
    tipo: Literal["be010"] = "be010"
    caminho: str
    conteudo: str | None = None
    regra: RegraBe010Spec


class AchadoBe010(BaseModel):
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


class SaidaBe010(BaseModel):
    achados: list[AchadoBe010] = Field(default_factory=list)


class EntradaInvalida(Exception):
    """Levantada quando `entrada` não satisfaz `EntradaBe010` — vira
    SCHEMA_REJECTION no Execution Engine (Vol.III Cap.12)."""


def _computar_fingerprint(
    agente: str, categoria: str, caminho: str, codigo: str, chave: str
) -> str:
    import hashlib

    normalizado = caminho.replace("\\", "/")
    bruto = f"{agente}|{categoria}|{normalizado}|{codigo}|{chave}"
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()


def _top_imports(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


def avaliar_be010(entrada: Any, contexto: ExecutionContext) -> Any:
    del contexto
    try:
        dados = EntradaBe010.model_validate(entrada)
    except Exception as exc:
        raise EntradaInvalida(str(exc)) from exc

    if dados.conteudo is None:
        return SaidaBe010(achados=[]).model_dump()

    payload = json.loads(dados.conteudo)
    pyproject_texto: str | None = payload.get("pyproject_texto")
    if pyproject_texto is None:
        return SaidaBe010(achados=[]).model_dump()
    pyproject_lower = pyproject_texto.lower()

    local_modules: set[str] = set(payload.get("local_modules", []))
    arquivos: dict[str, str] = payload.get("arquivos", {})

    seen: dict[str, str] = {}
    for caminho, texto in arquivos.items():
        try:
            tree = ast.parse(texto)
        except SyntaxError:
            continue
        for name in _top_imports(tree):
            if name in _STDLIB or name in local_modules or name.startswith("_"):
                continue
            if name.lower() in _KNOWN_TRANSITIVE:
                continue
            seen.setdefault(name, caminho)

    regra = dados.regra
    achados: list[AchadoBe010] = []
    for name, caminho_ocorrencia in sorted(seen.items()):
        if name.lower() in pyproject_lower:
            continue
        fingerprint = _computar_fingerprint(
            regra.agente, regra.categoria, caminho_ocorrencia, regra.codigo, name
        )
        achados.append(
            AchadoBe010(
                codigo=regra.codigo,
                agente=regra.agente,
                severidade=regra.severidade,
                categoria=regra.categoria,
                titulo=regra.titulo,
                descricao=(
                    f"'{name}' importado em {caminho_ocorrencia} mas ausente de pyproject.toml."
                ),
                causa=regra.causa,
                remediacao=regra.remediacao,
                arquivo=caminho_ocorrencia,
                chave=name,
                fingerprint=fingerprint,
            )
        )

    return SaidaBe010(achados=achados).model_dump()


def construir_implementacao() -> CapabilityImplementation:
    definicao = CapabilityDefinition(
        id=CapabilityId("be010-dependencia-nao-declarada"),
        name="BE-010 dependencia importada mas nao declarada",
        version="1.0.0",
        input_schema=EntradaBe010.model_json_schema(),
        output_schema=SaidaBe010.model_json_schema(),
        deterministic=True,
        side_effects=SideEffects.NONE,
        idempotent=True,
    )

    _regra_teste = {
        "codigo": "BE-010",
        "agente": "backend-engineer",
        "severidade": "low",
        "categoria": "imports",
        "titulo": "t",
        "causa": "c",
        "remediacao": "r",
    }
    entrada_sucesso = {
        "caminho": "pyproject.toml",
        "conteudo": json.dumps(
            {
                "pyproject_texto": "[project]\ndependencies = ['fastapi']\n",
                "local_modules": ["api", "src"],
                "arquivos": {"api/x.py": "import bcrypt\n"},
            }
        ),
        "regra": _regra_teste,
    }
    entrada_ok = {
        "caminho": "pyproject.toml",
        "conteudo": json.dumps(
            {
                "pyproject_texto": "[project]\ndependencies = ['bcrypt']\n",
                "local_modules": ["api", "src"],
                "arquivos": {"api/x.py": "import bcrypt\n"},
            }
        ),
        "regra": _regra_teste,
    }
    entrada_sem_pyproject = {
        "caminho": "pyproject.toml",
        "conteudo": None,
        "regra": _regra_teste,
    }

    return CapabilityImplementation(
        definition=definicao,
        handler=avaliar_be010,
        acceptance_tests=[
            AcceptanceTest(
                name="import-de-terceiro-nao-declarado-dispara-um-achado",
                entrada=entrada_sucesso,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: len(saida["achados"]) == 1,
            ),
            AcceptanceTest(
                name="import-declarado-nao-dispara",
                entrada=entrada_ok,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: saida["achados"] == [],
            ),
            AcceptanceTest(
                name="sem-pyproject-nao-dispara",
                entrada=entrada_sem_pyproject,
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
                    "caminho": "pyproject.toml",
                    "conteudo": "x",
                    "regra": {"severidade": 123},
                },
                resultado_esperado=ResultadoEsperado.TIMEOUT,
            ),
        ],
    )
