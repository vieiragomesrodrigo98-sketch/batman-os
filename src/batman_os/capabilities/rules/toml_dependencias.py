"""Skill "parsing TOML real de pyproject.toml" (Vol.IV Cap.17) — Milestone 3,
Skill 5.

Cobre DEP-001, DEP-002 (`Batman/scan/rules/dep_check.py`, já usam
`tomllib` real) e DEP-003/DEP-004 (mesmo módulo, mas hoje via regex sobre o
texto cru de `pyproject.toml` — **melhoria deliberada, não migração fiel**:
aqui os 4 usam `tomllib` real, mais preciso que regex sobre seção extraída
manualmente).

Handler continua puro: recebe o TEXTO de `pyproject.toml` (+ `requirements.
txt`, se existir — DEP-003 também checa esse arquivo no legado) + o
conteúdo dos arquivos `.py` relevantes (`tests/`, `src/`) já lidos por
`cli/descoberta_arquivos.py`, faz `tomllib.loads()` (parsing, não IO) e
`ast.parse()` sobre os arquivos internamente.
"""

from __future__ import annotations

import ast
import hashlib
import re
import sys
from enum import StrEnum
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

try:
    _STDLIB: frozenset[str] = frozenset(sys.stdlib_module_names)
except AttributeError:  # pragma: no cover - Python < 3.10
    _STDLIB = frozenset()

_LOCAL_PKGS = frozenset(
    {
        "api",
        "src",
        "radar",
        "governance",
        "config",
        "tests",
        "batman",
        "alfred",
        "scripts",
        "dashboard",
    }
)
_TRANSITIVE_OK = frozenset(
    {
        "starlette",
        "anyio",
        "pydantic_core",
        "annotated_types",
        "typing_extensions",
        "packaging",
        "exceptiongroup",
        "sniffio",
        "h11",
        "certifi",
        "charset_normalizer",
        "idna",
        "urllib3",
        "click",
        "email_validator",
        "cryptography",
        "ecdsa",
        "rsa",
        "cffi",
        "deprecated",
        "wrapt",
        "six",
    }
)
_IMPORT_TO_PKG: dict[str, str] = {
    "PIL": "pillow",
    "sklearn": "scikit_learn",
    "cv2": "opencv_python",
    "yaml": "pyyaml",
    "jose": "python_jose",
    "dotenv": "python_dotenv",
    "bs4": "beautifulsoup4",
    "dateutil": "python_dateutil",
    "multipart": "python_multipart",
    "Crypto": "pycryptodome",
    "webpush": "pywebpush",
    "jwt": "pyjwt",
}
_PARQUET_CALL = re.compile(r"\.(to_parquet|read_parquet)\s*\(")


class Aspecto(StrEnum):
    IMPORT_NAO_DECLARADO = "import_nao_declarado"
    PARQUET_SEM_ENGINE = "parquet_sem_engine"
    SEM_LIMITE_SUPERIOR = "sem_limite_superior"
    DUPLICADO_PROD_DEV = "duplicado_prod_dev"


class RegraDependenciasSpec(BaseModel):
    codigo: str
    agente: str
    severidade: str
    categoria: str
    titulo: str
    causa: str
    remediacao: str
    aspecto: Aspecto


class EntradaDependencias(BaseModel):
    tipo: Literal["toml-dependencias"] = "toml-dependencias"
    caminho: str
    conteudo: str | None = None
    regra: RegraDependenciasSpec


class AchadoDependencias(BaseModel):
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


class SaidaDependencias(BaseModel):
    achados: list[AchadoDependencias] = Field(default_factory=list)


class EntradaInvalida(Exception):
    """Levantada quando `entrada` não satisfaz `EntradaDependencias` — vira
    SCHEMA_REJECTION no Execution Engine (Vol.III Cap.12)."""


class _Payload(BaseModel):
    """Formato empacotado por `cli/descoberta_arquivos.py` (tipo de
    descoberta `"toml_dependencias"`) em `EntradaDependencias.conteudo`."""

    pyproject_texto: str | None = None
    requirements_texto: str | None = None
    arquivos_tests: dict[str, str] = Field(default_factory=dict)
    arquivos_src: dict[str, str] = Field(default_factory=dict)


def _computar_fingerprint(agente: str, categoria: str, caminho: str, codigo: str) -> str:
    normalizado = caminho.replace("\\", "/")
    bruto = f"{agente}|{categoria}|{normalizado}|{codigo}|"
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()


def _achado(regra: RegraDependenciasSpec, caminho: str, descricao: str) -> AchadoDependencias:
    fingerprint = _computar_fingerprint(regra.agente, regra.categoria, caminho, regra.codigo)
    return AchadoDependencias(
        codigo=regra.codigo,
        agente=regra.agente,
        severidade=regra.severidade,
        categoria=regra.categoria,
        titulo=regra.titulo,
        descricao=descricao,
        causa=regra.causa,
        remediacao=regra.remediacao,
        arquivo=caminho,
        fingerprint=fingerprint,
    )


def _norm(dep: str) -> str:
    nome = re.split(r"[><=!;\[\s]", dep.strip())[0]
    return nome.lower().replace("-", "_")


def _parse_toml(texto: str | None) -> dict[str, Any]:
    if not texto:
        return {}
    import tomllib

    try:
        return tomllib.loads(texto)
    except Exception:
        return {}


def _deps_declaradas(config: dict[str, Any]) -> set[str]:
    projeto = config.get("project", {})
    declaradas = {_norm(dep) for dep in projeto.get("dependencies", []) if _norm(dep)}
    for extras in projeto.get("optional-dependencies", {}).values():
        declaradas.update(_norm(dep) for dep in extras if _norm(dep))
    return declaradas


def _imports_top_level(source: str) -> list[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    nomes: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            nomes.extend(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            nomes.append(node.module.split(".")[0])
    return nomes


def _deve_pular(import_name: str) -> bool:
    return (
        not import_name
        or import_name.startswith("_")
        or import_name in _STDLIB
        or import_name in _LOCAL_PKGS
        or import_name.lower() in _TRANSITIVE_OK
    )


def _interpretar_import_nao_declarado(
    regra: RegraDependenciasSpec, caminho: str, payload: _Payload
) -> list[AchadoDependencias]:
    config = _parse_toml(payload.pyproject_texto)
    declaradas = _deps_declaradas(config)
    if not declaradas:
        return []

    ausentes: dict[str, list[str]] = {}
    for rel, source in sorted(payload.arquivos_tests.items()):
        for import_name in _imports_top_level(source):
            if _deve_pular(import_name):
                continue
            pkg = _IMPORT_TO_PKG.get(import_name, import_name).lower().replace("-", "_")
            if pkg not in declaradas:
                ausentes.setdefault(pkg, [])
                if rel not in ausentes[pkg]:
                    ausentes[pkg].append(rel)

    achados = []
    for pkg, arquivos in sorted(ausentes.items()):
        amostra = arquivos[:3]
        extra = f" (+{len(arquivos) - 3} mais)" if len(arquivos) > 3 else ""
        descricao = (
            f"'{pkg}' importado em tests/ mas ausente do pyproject.toml "
            f"({', '.join(amostra)}{extra})."
        )
        achados.append(_achado(regra, caminho, descricao))
    return achados


def _interpretar_parquet_sem_engine(
    regra: RegraDependenciasSpec, caminho: str, payload: _Payload
) -> list[AchadoDependencias]:
    config = _parse_toml(payload.pyproject_texto)
    declaradas = _deps_declaradas(config)
    if not declaradas:
        return []
    if "pyarrow" in declaradas or "fastparquet" in declaradas:
        return []

    achados = []
    todos_arquivos = {**payload.arquivos_tests, **payload.arquivos_src}
    for rel, source in sorted(todos_arquivos.items()):
        if _PARQUET_CALL.search(source):
            descricao = (
                f"{rel}: usa .to_parquet()/.read_parquet() mas nem pyarrow nem "
                f"fastparquet está em pyproject.toml."
            )
            achados.append(_achado(regra, rel, descricao))
    return achados


def _sem_limite_superior(dep_stripped: str) -> bool:
    return bool(re.search(r">=", dep_stripped) and not re.search(r"<|==|~=", dep_stripped))


def _interpretar_sem_limite_superior(
    regra: RegraDependenciasSpec, caminho: str, payload: _Payload
) -> list[AchadoDependencias]:
    config = _parse_toml(payload.pyproject_texto)
    projeto = config.get("project", {})
    ruins = []
    for dep in projeto.get("dependencies", []):
        dep_stripped = dep.strip()
        if _sem_limite_superior(dep_stripped):
            nome = re.split(r"[><=!;\[\s]", dep_stripped)[0]
            if nome:
                ruins.append(nome)

    # requirements.txt (se presente) segue o mesmo formato de dep-spec por
    # linha, embora não seja TOML — legado (dep_check.py) também checa esse
    # arquivo separadamente.
    for linha in (payload.requirements_texto or "").splitlines():
        linha_stripped = linha.strip()
        if not linha_stripped or linha_stripped.startswith("#"):
            continue
        if _sem_limite_superior(linha_stripped):
            nome = re.split(r"[><=!;\[\s]", linha_stripped)[0]
            if nome:
                ruins.append(f"requirements.txt:{nome}")

    if not ruins:
        return []
    descricao = f"Dependências sem limite superior de versão: {', '.join(ruins)}."
    return [_achado(regra, caminho, descricao)]


def _interpretar_duplicado_prod_dev(
    regra: RegraDependenciasSpec, caminho: str, payload: _Payload
) -> list[AchadoDependencias]:
    config = _parse_toml(payload.pyproject_texto)
    projeto = config.get("project", {})
    prod = {_norm(dep) for dep in projeto.get("dependencies", []) if _norm(dep)}
    dev = {
        _norm(dep) for dep in projeto.get("optional-dependencies", {}).get("dev", []) if _norm(dep)
    }
    duplicados = sorted(prod & dev)
    if not duplicados:
        return []
    descricao = f"Pacotes declarados em produção e dev simultaneamente: {', '.join(duplicados)}."
    return [_achado(regra, caminho, descricao)]


_DISPATCH = {
    Aspecto.IMPORT_NAO_DECLARADO: _interpretar_import_nao_declarado,
    Aspecto.PARQUET_SEM_ENGINE: _interpretar_parquet_sem_engine,
    Aspecto.SEM_LIMITE_SUPERIOR: _interpretar_sem_limite_superior,
    Aspecto.DUPLICADO_PROD_DEV: _interpretar_duplicado_prod_dev,
}


def avaliar_regra_dependencias(entrada: Any, contexto: ExecutionContext) -> Any:
    del contexto
    try:
        dados = EntradaDependencias.model_validate(entrada)
    except Exception as exc:
        raise EntradaInvalida(str(exc)) from exc

    if dados.conteudo is None:
        return SaidaDependencias(achados=[]).model_dump()

    try:
        import json as _json

        payload = _Payload.model_validate(_json.loads(dados.conteudo))
    except Exception:
        return SaidaDependencias(achados=[]).model_dump()

    interprete = _DISPATCH[dados.regra.aspecto]
    achados = interprete(dados.regra, dados.caminho, payload)
    return SaidaDependencias(achados=achados).model_dump()


def construir_implementacao() -> CapabilityImplementation:
    definicao = CapabilityDefinition(
        id=CapabilityId("toml-dependencias"),
        name="Dependencias declaradas em pyproject.toml (TOML real)",
        version="1.0.0",
        input_schema=EntradaDependencias.model_json_schema(),
        output_schema=SaidaDependencias.model_json_schema(),
        deterministic=True,
        side_effects=SideEffects.NONE,
        idempotent=True,
    )

    import json as _json

    regra_teste = {
        "codigo": "TEST-DEP-001",
        "agente": "teste",
        "severidade": "high",
        "categoria": "teste",
        "titulo": "teste",
        "causa": "teste",
        "remediacao": "teste",
        "aspecto": "import_nao_declarado",
    }
    entrada_sucesso = {
        "caminho": "pyproject.toml",
        "conteudo": _json.dumps(
            {
                "pyproject_texto": '[project]\ndependencies = ["fastapi>=0.1"]\n',
                "arquivos_tests": {"tests/test_a.py": "import pyarrow\n"},
                "arquivos_src": {},
            }
        ),
        "regra": regra_teste,
    }
    entrada_conteudo_malformado = {
        "caminho": "pyproject.toml",
        "conteudo": "nao e json",
        "regra": regra_teste,
    }
    entrada_regra_invalida = {
        "caminho": "pyproject.toml",
        "conteudo": _json.dumps({"pyproject_texto": None}),
        "regra": {**regra_teste, "aspecto": "nao-existe"},
    }

    return CapabilityImplementation(
        definition=definicao,
        handler=avaliar_regra_dependencias,
        acceptance_tests=[
            AcceptanceTest(
                name="import-nao-declarado-dispara",
                entrada=entrada_sucesso,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: len(saida["achados"]) == 1,
            ),
            AcceptanceTest(
                name="entrada-sem-campo-obrigatorio-e-rejeitada",
                entrada={"caminho": "pyproject.toml"},
                resultado_esperado=ResultadoEsperado.SCHEMA_REJECTION,
            ),
            AcceptanceTest(
                name="conteudo-malformado-nao-quebra-o-handler",
                entrada=entrada_conteudo_malformado,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: saida["achados"] == [],
            ),
            AcceptanceTest(
                name="aspecto_desconhecido_e_tratado_como_falha_de_invocacao",
                entrada=entrada_regra_invalida,
                resultado_esperado=ResultadoEsperado.TIMEOUT,
            ),
        ],
    )
