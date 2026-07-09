"""Capability bespoke REV-005 "bloco de código duplicado (8+ linhas
idênticas em dois arquivos distintos)" (Vol.IV Cap.17).

Não generalizada em Skill — precisa de agregação CRUZADA entre TODOS os
arquivos candidatos (até 20, de `api/` depois `src/radar/`, > 50 linhas,
sem test/migration/alembic no caminho): normaliza cada janela de 8 linhas,
faz hash, agrupa por hash através de TODOS os arquivos, e reporta o
PRIMEIRO par de arquivos distintos que compartilham uma janela idêntica —
com de-dup GLOBAL por par de arquivos (não por hash), respeitando a ordem
de descoberta. Mesmo espírito de agregação de `ora004_status_typo.py`
(uma única invocação processa todos os arquivos e pode produzir MÚLTIPLOS
achados), mas aqui o payload de entrada já vem pré-filtrado pela
descoberta (`_resultado_rev005` em `descoberta_arquivos.py`)."""

from __future__ import annotations

import hashlib
import json
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

_WINDOW = 8
_IMPORT_RE = re.compile(r"^(?:import |from \w)")


class RegraRev005Spec(BaseModel):
    codigo: str
    agente: str
    severidade: str
    categoria: str
    titulo: str
    causa: str
    remediacao: str


class EntradaRev005(BaseModel):
    tipo: Literal["rev005"] = "rev005"
    caminho: str
    conteudo: str | None = None
    regra: RegraRev005Spec


class AchadoRev005(BaseModel):
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


class SaidaRev005(BaseModel):
    achados: list[AchadoRev005] = Field(default_factory=list)


class EntradaInvalida(Exception):
    """Levantada quando `entrada` não satisfaz `EntradaRev005` — vira
    SCHEMA_REJECTION no Execution Engine (Vol.III Cap.12)."""


def _computar_fingerprint(agente: str, categoria: str, caminho: str, codigo: str) -> str:
    normalizado = caminho.replace("\\", "/")
    bruto = f"{agente}|{categoria}|{normalizado}|{codigo}|"
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()


def _normalize(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip()


def _is_import_block(window: list[str]) -> bool:
    non_blank = [ln for ln in window if ln.strip()]
    if not non_blank:
        return True
    import_lines = sum(1 for ln in non_blank if _IMPORT_RE.match(ln.strip()))
    return import_lines / len(non_blank) >= 0.6


def _encontrar_pares_duplicados(arquivos: dict[str, str]) -> list[tuple[str, int, str, int]]:
    """Retorna `[(rel1, linha1, rel2, linha2), ...]` — um por par de
    arquivos distintos que compartilha ao menos uma janela de 8 linhas
    idêntica (normalizada), na ordem de descoberta, de-duplicado
    globalmente por par de arquivos."""
    hash_map: dict[str, list[tuple[str, int]]] = {}
    for rel, conteudo in arquivos.items():
        lines = conteudo.splitlines()
        for i in range(len(lines) - _WINDOW + 1):
            window = lines[i : i + _WINDOW]
            if _is_import_block(window):
                continue
            normalized = "\n".join(_normalize(ln) for ln in window)
            if not normalized.strip():
                continue
            key = hashlib.sha1(normalized.encode()).hexdigest()
            if key not in hash_map:
                hash_map[key] = []
            hash_map[key].append((rel, i + 1))

    reported: set[str] = set()
    pares: list[tuple[str, int, str, int]] = []
    for occurrences in hash_map.values():
        files_seen: dict[str, tuple[str, int]] = {}
        for rel, lineno in occurrences:
            if rel not in files_seen:
                files_seen[rel] = (rel, lineno)
        if len(files_seen) >= 2:
            file_list = list(files_seen.values())
            pair_key = "|".join(sorted(rel for rel, _ in file_list[:2]))
            if pair_key in reported:
                continue
            reported.add(pair_key)
            rel1, l1 = file_list[0]
            rel2, l2 = file_list[1]
            pares.append((rel1, l1, rel2, l2))
    return pares


def avaliar_rev005(entrada: Any, contexto: ExecutionContext) -> Any:
    del contexto
    try:
        dados = EntradaRev005.model_validate(entrada)
    except Exception as exc:
        raise EntradaInvalida(str(exc)) from exc

    if dados.conteudo is None:
        return SaidaRev005(achados=[]).model_dump()

    payload = json.loads(dados.conteudo)
    arquivos: dict[str, str] = payload["arquivos"]

    pares = _encontrar_pares_duplicados(arquivos)
    if not pares:
        return SaidaRev005(achados=[]).model_dump()

    regra = dados.regra
    achados: list[AchadoRev005] = []
    for rel1, l1, rel2, l2 in pares:
        fingerprint = _computar_fingerprint(regra.agente, regra.categoria, rel1, regra.codigo)
        achados.append(
            AchadoRev005(
                codigo=regra.codigo,
                agente=regra.agente,
                severidade=regra.severidade,
                categoria=regra.categoria,
                titulo=regra.titulo,
                descricao=f"Bloco duplicado: {rel1}:{l1} e {rel2}:{l2} ({_WINDOW} linhas).",
                causa=regra.causa,
                remediacao=regra.remediacao,
                arquivo=rel1,
                fingerprint=fingerprint,
            )
        )

    return SaidaRev005(achados=achados).model_dump()


def construir_implementacao() -> CapabilityImplementation:
    definicao = CapabilityDefinition(
        id=CapabilityId("rev005-bloco-duplicado"),
        name="REV-005 bloco de codigo duplicado",
        version="1.0.0",
        input_schema=EntradaRev005.model_json_schema(),
        output_schema=SaidaRev005.model_json_schema(),
        deterministic=True,
        side_effects=SideEffects.NONE,
        idempotent=True,
    )

    _regra_teste = {
        "codigo": "REV-005",
        "agente": "code-reviewer",
        "severidade": "low",
        "categoria": "manutenibilidade",
        "titulo": "t",
        "causa": "c",
        "remediacao": "r",
    }
    bloco = "\n".join(f"linha_{i} = {i}" for i in range(10))
    entrada_sucesso = {
        "caminho": ".",
        "conteudo": json.dumps({"arquivos": {"a.py": bloco, "b.py": bloco}}),
        "regra": _regra_teste,
    }
    entrada_ok = {
        "caminho": ".",
        "conteudo": json.dumps({"arquivos": {"a.py": "x = 1\n", "b.py": "y = 2\n"}}),
        "regra": _regra_teste,
    }

    return CapabilityImplementation(
        definition=definicao,
        handler=avaliar_rev005,
        acceptance_tests=[
            AcceptanceTest(
                name="bloco-de-8-linhas-duplicado-entre-arquivos-dispara",
                entrada=entrada_sucesso,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: len(saida["achados"]) == 1,
            ),
            AcceptanceTest(
                name="arquivos-sem-bloco-duplicado-nao-dispara",
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
                    "caminho": ".",
                    "conteudo": "x",
                    "regra": {"severidade": 123},
                },
                resultado_esperado=ResultadoEsperado.TIMEOUT,
            ),
        ],
    )
