"""Capability bespoke — DE-003 (Vol.IV Cap.17) — Milestone 3, Skill 6.

O mais complexo do catálogo migrado (`Batman/scan/rules/data_engineer.py`):
cruza `git log -p` (histórico de mudanças em `tables.py`) com o registro de
migrations em `init_db.py` para achar colunas SQLAlchemy adicionadas via
ALTER TABLE implícito (`mapped_column(nullable=True|default=...)`) sem
entrada correspondente em `_NEW_*_COLUMNS`. Não generalizado em Skill — o
padrão (parser de diff unificado com máquina de estados por classe/commit)
não se repete em nenhuma outra regra migrada.

Handler continua puro: recebe o texto de `init_db.py`/`tables.py` e a saída
já capturada de `git log -p` (o `subprocess` roda em
`cli/descoberta_arquivos.py`, mesmo padrão das demais Skills)."""

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

AGENTE = "data-engineer"
CATEGORIA = "versionamento-schema"
CODIGO = "DE-003"


class RegraDe003Spec(BaseModel):
    codigo: str = CODIGO
    agente: str = AGENTE
    severidade: str = "high"
    categoria: str = CATEGORIA
    titulo: str = "Coluna SQLAlchemy adicionada sem entrada em _NEW_*_COLUMNS (init_db.py)"
    causa: str = (
        "Adicionar mapped_column() com nullable=True ou default= a uma tabela existente "
        "sem registrar a coluna em _NEW_*_COLUMNS do init_db.py causa OperationalError "
        "em bancos existentes (staging/produção): a coluna existe no ORM mas não na "
        "tabela real, quebrando queries e endpoints que dependem dela."
    )
    remediacao: str = (
        "1. Adicionar ('nome_col', 'TIPO SQL') à lista _NEW_*_COLUMNS correspondente em "
        "api/database/init_db.py (criar nova lista se a tabela não tiver cobertura). "
        "2. Rodar: python scripts/init_staging_db.py --copy. "
        "3. Verificar: data/migration_changelog.json registra a coluna. "
        "DoD: DE-003 some do relatório Batman após o commit que corrige."
    )


class EntradaDe003(BaseModel):
    tipo: Literal["de003"] = "de003"
    caminho: str
    conteudo: str | None = None
    regra: RegraDe003Spec = Field(default_factory=RegraDe003Spec)


class AchadoDe003(BaseModel):
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


class SaidaDe003(BaseModel):
    achados: list[AchadoDe003] = Field(default_factory=list)


class EntradaInvalida(Exception):
    """Levantada quando `entrada` não satisfaz `EntradaDe003` — vira
    SCHEMA_REJECTION no Execution Engine (Vol.III Cap.12)."""


class _Payload(BaseModel):
    aplica: bool = False
    init_db_src: str = ""
    tables_src: str = ""
    git_log: str = ""


def _computar_fingerprint(caminho: str, chave: str) -> str:
    normalizado = caminho.replace("\\", "/")
    bruto = f"{AGENTE}|{CATEGORIA}|{normalizado}|{CODIGO}|{chave}"
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()


def _parse_migration_cols(src: str) -> set[str]:
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return set()
    cols: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not (
                isinstance(target, ast.Name)
                and target.id.startswith("_NEW_")
                and target.id.endswith("_COLUMNS")
            ):
                continue
            if not isinstance(node.value, ast.List):
                continue
            for elt in node.value.elts:
                if (
                    isinstance(elt, ast.Tuple)
                    and elt.elts
                    and isinstance(elt.elts[0], ast.Constant)
                    and isinstance(elt.elts[0].value, str)
                ):
                    cols.add(elt.elts[0].value)
    return cols


def _parse_covered_tables(src: str) -> set[str]:
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return set()
    tabelas: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_migrate_table"
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
        ):
            tabelas.add(node.args[1].value)
    return tabelas


def _parse_class_to_table(src: str) -> dict[str, str]:
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return {}
    resultado: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for item in node.body:
            if (
                isinstance(item, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "__tablename__" for t in item.targets)
                and isinstance(item.value, ast.Constant)
                and isinstance(item.value.value, str)
            ):
                resultado[node.name] = item.value.value
    return resultado


def _extract_late_col(content: str) -> str | None:
    if "mapped_column(" not in content:
        return None
    if "nullable=True" not in content and "default=" not in content:
        return None
    m = re.match(r"\s+(\w+)\s*:\s*Mapped\[", content)
    return m.group(1) if m else None


def _detectar(payload: _Payload) -> tuple[dict[str, str], dict[str, str]]:
    """Máquina de estados sobre `git log -p` — replica exatamente o loop de
    `DataEngineer.detect()` (linha a linha, rastreia classe/commit atuais).
    Retorna (unregistered_high, unregistered_med): coluna -> commit."""
    migration_cols = _parse_migration_cols(payload.init_db_src)
    covered_tables = _parse_covered_tables(payload.init_db_src)
    class_to_table = _parse_class_to_table(payload.tables_src)

    current_commit = ""
    current_class_ctx: str | None = None
    new_table_classes: set[str] = set()
    unregistered_high: dict[str, str] = {}
    unregistered_med: dict[str, str] = {}
    removed_cols: set[str] = set()

    for line in payload.git_log.splitlines():
        if line.startswith("COMMIT:"):
            current_commit = line[7:15]
        elif line.startswith("@@") and "class " in line:
            m = re.search(r"class (\w+)\s*\(", line)
            if m:
                current_class_ctx = m.group(1)
        elif line.startswith(" class ") and "Base" in line:
            m = re.match(r" class (\w+)\s*\(", line)
            if m:
                current_class_ctx = m.group(1)
        elif line.startswith("+class ") and "Base" in line:
            m = re.match(r"\+class (\w+)\s*\(", line)
            if m:
                new_table_classes.add(m.group(1))
                current_class_ctx = m.group(1)
        elif line.startswith("+") and not line.startswith("+++"):
            col = _extract_late_col(line[1:])
            if not col or col in migration_cols or col in removed_cols:
                continue
            if current_class_ctx in new_table_classes:
                continue
            tabela = class_to_table.get(current_class_ctx) if current_class_ctx else None
            if tabela in covered_tables:
                unregistered_high.setdefault(col, current_commit)
            elif tabela is not None:
                unregistered_med.setdefault(col, current_commit)
        elif line.startswith("-") and not line.startswith("---"):
            col = _extract_late_col(line[1:])
            if col:
                removed_cols.add(col)
                unregistered_high.pop(col, None)
                unregistered_med.pop(col, None)

    return unregistered_high, unregistered_med


def avaliar_de003(entrada: Any, contexto: ExecutionContext) -> Any:
    del contexto
    try:
        dados = EntradaDe003.model_validate(entrada)
    except Exception as exc:
        raise EntradaInvalida(str(exc)) from exc

    if dados.conteudo is None:
        return SaidaDe003(achados=[]).model_dump()

    try:
        import json

        payload = _Payload.model_validate(json.loads(dados.conteudo))
    except Exception:
        return SaidaDe003(achados=[]).model_dump()

    if not payload.aplica or not payload.git_log:
        return SaidaDe003(achados=[]).model_dump()

    regra = dados.regra
    unregistered_high, unregistered_med = _detectar(payload)

    achados = []
    if unregistered_high:
        itens = ", ".join(f"{c} ({v})" for c, v in sorted(unregistered_high.items()))
        descricao = (
            f"{len(unregistered_high)} coluna(s) adicionada(s) a tabela(s) com cobertura "
            f"de migration sem entrada em _NEW_*_COLUMNS de init_db.py: {itens}."
        )
        achados.append(
            AchadoDe003(
                codigo=regra.codigo,
                agente=regra.agente,
                severidade=regra.severidade,
                categoria=regra.categoria,
                titulo=regra.titulo,
                descricao=descricao,
                causa=regra.causa,
                remediacao=regra.remediacao,
                arquivo=dados.caminho,
                chave="DE003-covered-missing",
                fingerprint=_computar_fingerprint(dados.caminho, "DE003-covered-missing"),
            )
        )
    if unregistered_med:
        itens = ", ".join(f"{c} ({v})" for c, v in sorted(unregistered_med.items()))
        descricao = (
            f"{len(unregistered_med)} coluna(s) adicionada(s) a tabela(s) SEM cobertura de "
            f"migration em init_db.py: {itens}. Se a tabela já existe em staging/prod, "
            f"adicionar _migrate_table()."
        )
        achados.append(
            AchadoDe003(
                codigo=regra.codigo,
                agente=regra.agente,
                severidade=regra.severidade,
                categoria=regra.categoria,
                titulo=regra.titulo,
                descricao=descricao,
                causa=regra.causa,
                remediacao=regra.remediacao,
                arquivo=dados.caminho,
                chave="DE003-uncovered-risk",
                fingerprint=_computar_fingerprint(dados.caminho, "DE003-uncovered-risk"),
            )
        )
    return SaidaDe003(achados=achados).model_dump()


def construir_implementacao() -> CapabilityImplementation:
    definicao = CapabilityDefinition(
        id=CapabilityId("de003-coluna-sem-migration"),
        name="DE-003: coluna SQLAlchemy adicionada sem migration registrada",
        version="1.0.0",
        input_schema=EntradaDe003.model_json_schema(),
        output_schema=SaidaDe003.model_json_schema(),
        deterministic=True,
        side_effects=SideEffects.NONE,
        idempotent=True,
    )

    init_db_src = "_NEW_FOO_COLUMNS = [('bar', 'TEXT')]\n\ndef f():\n    _migrate_table(x, 'foo')\n"
    tables_src = "class Foo(Base):\n    __tablename__ = 'foo'\n"
    git_log_dispara = (
        "COMMIT:abc12345\n"
        "@@ -1,3 +1,4 @@ class Foo(\n"
        " class Foo(Base):\n"
        '     __tablename__ = "foo"\n'
        "+    nova_coluna: Mapped[str] = mapped_column(nullable=True)\n"
    )
    import json

    entrada_sucesso = {
        "caminho": "api/database/tables.py",
        "conteudo": json.dumps(
            {
                "aplica": True,
                "init_db_src": init_db_src,
                "tables_src": tables_src,
                "git_log": git_log_dispara,
            }
        ),
        "regra": {},
    }
    entrada_nao_aplica = {
        "caminho": "api/database/tables.py",
        "conteudo": json.dumps({"aplica": False}),
        "regra": {},
    }
    entrada_conteudo_malformado = {
        "caminho": "api/database/tables.py",
        "conteudo": "nao e json",
        "regra": {},
    }
    entrada_regra_invalida = {
        "caminho": "api/database/tables.py",
        "conteudo": json.dumps({"aplica": True, "git_log": "x"}),
        "regra": {"severidade": 123},
    }

    return CapabilityImplementation(
        definition=definicao,
        handler=avaliar_de003,
        acceptance_tests=[
            AcceptanceTest(
                name="coluna-tardia-sem-migration-dispara",
                entrada=entrada_sucesso,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: len(saida["achados"]) == 1,
            ),
            AcceptanceTest(
                name="nao-aplica-retorna-vazio",
                entrada=entrada_nao_aplica,
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
