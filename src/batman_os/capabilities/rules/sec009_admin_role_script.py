"""Capability bespoke SEC-009 "script cria admin/super_admin via SQL
direto ou ORM fora da API" (Vol.IV Cap.17).

Não generalizada em `janela_contexto_regex` — DOIS padrões de disparo
INDEPENDENTES na MESMA regra, cada um com sua própria mensagem, e `break`
no PRIMEIRO match (qualquer um dos dois) por ARQUIVO — não é "achar
todas as ocorrências", é "parar no primeiro sinal". Além disso: exclusão
por nome de arquivo exato (`create_prod_users.py`, já bloqueado por
outra camada) e um gate de arquivo inteiro (só analisa arquivos que
realmente usam conexão de banco, via `_DB_USE`)."""

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

_INSERT_RE = re.compile(r"INSERT\s+INTO", re.I)
_ORM_ROLE = re.compile(r"\.role\s*=\s*['\"](?:super_admin|admin)['\"]")
_ADMIN_STR = re.compile(r"['\"](?:super_admin|admin)['\"]")
_DB_USE = re.compile(r"sqlite3\.connect|\.execute\s*\(|get_db\b|Session\b")
_ARQUIVO_EXCLUIDO = "create_prod_users.py"


class RegraSec009Spec(BaseModel):
    codigo: str
    agente: str
    severidade: str
    categoria: str
    titulo: str
    causa: str
    remediacao: str


class EntradaSec009(BaseModel):
    tipo: Literal["sec009"] = "sec009"
    caminho: str
    conteudo: str | None = None
    regra: RegraSec009Spec


class AchadoSec009(BaseModel):
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


class SaidaSec009(BaseModel):
    achados: list[AchadoSec009] = Field(default_factory=list)


class EntradaInvalida(Exception):
    """Levantada quando `entrada` não satisfaz `EntradaSec009` — vira
    SCHEMA_REJECTION no Execution Engine (Vol.III Cap.12)."""


def _computar_fingerprint(agente: str, categoria: str, caminho: str, codigo: str) -> str:
    import hashlib

    normalizado = caminho.replace("\\", "/")
    bruto = f"{agente}|{categoria}|{normalizado}|{codigo}|"
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()


def avaliar_sec009(entrada: Any, contexto: ExecutionContext) -> Any:
    del contexto
    try:
        dados = EntradaSec009.model_validate(entrada)
    except Exception as exc:
        raise EntradaInvalida(str(exc)) from exc

    nome_arquivo = dados.caminho.replace("\\", "/").rsplit("/", 1)[-1]
    if nome_arquivo == _ARQUIVO_EXCLUIDO:
        return SaidaSec009(achados=[]).model_dump()

    if dados.conteudo is None:
        return SaidaSec009(achados=[]).model_dump()

    text = dados.conteudo
    if not _DB_USE.search(text):
        return SaidaSec009(achados=[]).model_dump()

    regra = dados.regra
    lines = text.splitlines()
    descricao: str | None = None
    linha_achado: int | None = None

    for i, line in enumerate(lines):
        if _INSERT_RE.search(line):
            window = "\n".join(lines[i : i + 6])
            if _ADMIN_STR.search(window):
                descricao = f"{dados.caminho} linha {i + 1}: INSERT SQL com role admin/super_admin."
                linha_achado = i + 1
                break
        if _ORM_ROLE.search(line):
            descricao = (
                f"{dados.caminho} linha {i + 1}: atribuição direta de role admin via ORM em script."
            )
            linha_achado = i + 1
            break

    if descricao is None or linha_achado is None:
        return SaidaSec009(achados=[]).model_dump()

    fingerprint = _computar_fingerprint(regra.agente, regra.categoria, dados.caminho, regra.codigo)
    achado = AchadoSec009(
        codigo=regra.codigo,
        agente=regra.agente,
        severidade=regra.severidade,
        categoria=regra.categoria,
        titulo=regra.titulo,
        descricao=descricao,
        causa=regra.causa,
        remediacao=regra.remediacao,
        arquivo=dados.caminho,
        fingerprint=fingerprint,
    )
    return SaidaSec009(achados=[achado]).model_dump()


def construir_implementacao() -> CapabilityImplementation:
    definicao = CapabilityDefinition(
        id=CapabilityId("sec009-admin-role-script"),
        name="SEC-009 script cria admin/super_admin fora da API",
        version="1.0.0",
        input_schema=EntradaSec009.model_json_schema(),
        output_schema=SaidaSec009.model_json_schema(),
        deterministic=True,
        side_effects=SideEffects.NONE,
        idempotent=True,
    )

    _regra_teste = {
        "codigo": "SEC-009",
        "agente": "security-engineer",
        "severidade": "high",
        "categoria": "access-control",
        "titulo": "t",
        "causa": "c",
        "remediacao": "r",
    }
    entrada_sucesso = {
        "caminho": "scripts/promote_user.py",
        "conteudo": (
            "conn = sqlite3.connect('x.db')\n"
            "conn.execute(\"INSERT INTO users (role) VALUES ('admin')\")\n"
        ),
        "regra": _regra_teste,
    }
    entrada_ok = {
        "caminho": "scripts/promote_user.py",
        "conteudo": "conn = sqlite3.connect('x.db')\nconn.execute('SELECT 1')\n",
        "regra": _regra_teste,
    }

    return CapabilityImplementation(
        definition=definicao,
        handler=avaliar_sec009,
        acceptance_tests=[
            AcceptanceTest(
                name="insert-sql-com-role-admin-dispara",
                entrada=entrada_sucesso,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: len(saida["achados"]) == 1,
            ),
            AcceptanceTest(
                name="script-sem-role-admin-nao-dispara",
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
                    "caminho": "scripts/x.py",
                    "conteudo": "x",
                    "regra": {"severidade": 123},
                },
                resultado_esperado=ResultadoEsperado.TIMEOUT,
            ),
        ],
    )
