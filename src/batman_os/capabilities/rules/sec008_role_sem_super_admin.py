"""Capability bespoke SEC-008 "endpoint de alteração de role sem guarda
super_admin" (Vol.IV Cap.17).

Não generalizada em `janela_contexto_regex` — o gate de disparo é um OR
entre DOIS ESCOPOS DIFERENTES: `route_has_role` checa só a LINHA da rota
(`@router.patch/post(...)`), `sig_has_role` checa a JANELA de 20 linhas
inteira (decorator + assinatura) — a Skill não modela "trigger na linha
OU padrão na janela" como alternativas, só janela única. Múltiplos
achados por arquivo possíveis (1 por linha de rota elegível), sem
`chave` — colapsam ao mesmo fingerprint (mesma equivalência já
estabelecida para outros códigos)."""

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

_ROUTE_LINE = re.compile(r"@router\.(patch|post)", re.I)
_ROLE_ROUTE = re.compile(r'@router\.(patch|post)\s*\(\s*["\'][^"\']*role[^"\']*["\']', re.I)
_ROLE_PARAM = re.compile(r"def\s+\w+\s*\([^)]*\brole\b\s*:", re.I)
_SUPER_CHECK = re.compile(r"super_admin")


class RegraSec008Spec(BaseModel):
    codigo: str
    agente: str
    severidade: str
    categoria: str
    titulo: str
    causa: str
    remediacao: str


class EntradaSec008(BaseModel):
    tipo: Literal["sec008"] = "sec008"
    caminho: str
    conteudo: str | None = None
    regra: RegraSec008Spec


class AchadoSec008(BaseModel):
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


class SaidaSec008(BaseModel):
    achados: list[AchadoSec008] = Field(default_factory=list)


class EntradaInvalida(Exception):
    """Levantada quando `entrada` não satisfaz `EntradaSec008` — vira
    SCHEMA_REJECTION no Execution Engine (Vol.III Cap.12)."""


def _computar_fingerprint(agente: str, categoria: str, caminho: str, codigo: str) -> str:
    import hashlib

    normalizado = caminho.replace("\\", "/")
    bruto = f"{agente}|{categoria}|{normalizado}|{codigo}|"
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()


def avaliar_sec008(entrada: Any, contexto: ExecutionContext) -> Any:
    del contexto
    try:
        dados = EntradaSec008.model_validate(entrada)
    except Exception as exc:
        raise EntradaInvalida(str(exc)) from exc

    if dados.conteudo is None:
        return SaidaSec008(achados=[]).model_dump()

    text = dados.conteudo
    if "require_admin" not in text:
        return SaidaSec008(achados=[]).model_dump()

    regra = dados.regra
    lines = text.splitlines()
    achados: list[AchadoSec008] = []

    for i, line in enumerate(lines):
        if not _ROUTE_LINE.search(line):
            continue
        snippet = "\n".join(lines[i : i + 20])
        route_has_role = _ROLE_ROUTE.search(line)
        sig_has_role = _ROLE_PARAM.search(snippet)
        if not (route_has_role or sig_has_role):
            continue
        if "require_admin" not in snippet:
            continue
        if _SUPER_CHECK.search(snippet):
            continue

        fingerprint = _computar_fingerprint(
            regra.agente, regra.categoria, dados.caminho, regra.codigo
        )
        achados.append(
            AchadoSec008(
                codigo=regra.codigo,
                agente=regra.agente,
                severidade=regra.severidade,
                categoria=regra.categoria,
                titulo=regra.titulo,
                descricao=(
                    f"{dados.caminho} linha {i + 1}: endpoint de role sem verificação super_admin."
                ),
                causa=regra.causa,
                remediacao=regra.remediacao,
                arquivo=dados.caminho,
                fingerprint=fingerprint,
            )
        )

    return SaidaSec008(achados=achados).model_dump()


def construir_implementacao() -> CapabilityImplementation:
    definicao = CapabilityDefinition(
        id=CapabilityId("sec008-role-sem-super-admin"),
        name="SEC-008 endpoint de role sem guarda super_admin",
        version="1.0.0",
        input_schema=EntradaSec008.model_json_schema(),
        output_schema=SaidaSec008.model_json_schema(),
        deterministic=True,
        side_effects=SideEffects.NONE,
        idempotent=True,
    )

    _regra_teste = {
        "codigo": "SEC-008",
        "agente": "security-engineer",
        "severidade": "high",
        "categoria": "access-control",
        "titulo": "t",
        "causa": "c",
        "remediacao": "r",
    }
    entrada_sucesso = {
        "caminho": "api/routers/usuarios.py",
        "conteudo": (
            '@router.patch("/usuarios/{id}/role")\n'
            "def alterar_role(id: int, role: str, _=Depends(require_admin)):\n"
            "    pass\n"
        ),
        "regra": _regra_teste,
    }
    entrada_ok = {
        "caminho": "api/routers/usuarios.py",
        "conteudo": (
            '@router.patch("/usuarios/{id}/role")\n'
            "def alterar_role(id: int, role: str, _=Depends(require_admin)):\n"
            "    if current.role != 'super_admin':\n"
            "        raise HTTPException(403)\n"
        ),
        "regra": _regra_teste,
    }

    return CapabilityImplementation(
        definition=definicao,
        handler=avaliar_sec008,
        acceptance_tests=[
            AcceptanceTest(
                name="endpoint-de-role-sem-super-admin-dispara",
                entrada=entrada_sucesso,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: len(saida["achados"]) == 1,
            ),
            AcceptanceTest(
                name="endpoint-com-verificacao-super-admin-nao-dispara",
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
                    "caminho": "api/routers/x.py",
                    "conteudo": "x",
                    "regra": {"severidade": 123},
                },
                resultado_esperado=ResultadoEsperado.TIMEOUT,
            ),
        ],
    )
