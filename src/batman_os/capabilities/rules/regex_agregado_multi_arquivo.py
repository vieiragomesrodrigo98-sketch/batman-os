"""Skill "regex agregado sobre múltiplos arquivos" (Vol.IV Cap.17).

Generaliza o padrão que se repete em ~8 códigos da continuação da migração
do Batman legado (AI-003, COMP-005, IR-004, LEGAL-002, PD-012, SRE-001,
UXR-003, VPS-012): o legado concatena o conteúdo de VÁRIOS arquivos (escopo
fixo — `api_dir`, `frontend_dirs`, `scripts/*.sh`, ou todo `src_dirs`) e
produz NO MÁXIMO 1 achado (não por arquivo) se um padrão está ausente (ou
presente) em QUALQUER lugar da união dos arquivos — replica
`for p in dir: if padrao in texto: return` (early-exit "já encontrou, OK")
e `if padrao not in combined: yield finding` (concatenação prévia).

`pattern_2` (opcional): replica LEGAL-002 — 2 checagens de ausência
INDEPENDENTES no modo `ausencia` (termos de uso ausentes OU política de
privacidade ausente); como nenhuma delas define `chave` no legado, ambas
produzem o MESMO fingerprint (chave vazia) — então "pattern OU pattern_2
ausente" já é equivalente à união dos 2 achados possíveis do legado para
fins de comparação de fingerprint (SET, não lista)."""

from __future__ import annotations

import hashlib
import json
import re
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


class ModoAgregado(StrEnum):
    PRESENCA = "presenca"
    AUSENCIA = "ausencia"


class RegraAgregadaSpec(BaseModel):
    codigo: str
    agente: str
    severidade: str
    categoria: str
    titulo: str
    causa: str
    remediacao: str
    modo: ModoAgregado
    pattern: str
    pattern_2: str | None = None
    caminho_relatado: str
    ignore_case: bool = False


class EntradaAgregada(BaseModel):
    """`tipo` é o mesmo discriminador estrutural das outras Entradas desta
    migração — evita colisão de schema em `CapabilityRegistry.
    find_candidates` (achado de auditoria da validação final do lote
    Milestones 2-7: capabilities com o mesmo conjunto de chaves de
    top-level empatavam como candidatas para a mesma entrada, corrigido em
    `capability_engine._schema_compativel` — agora também checa o VALOR de
    `tipo`, não só a presença da chave).

    `conteudo` (JSON serializado, mesmo padrão de `EntradaOra004`/
    `EntradaDe003`): parsing da estrutura `{"arquivos": {caminho: texto}}`
    acontece no HANDLER, não na camada de descoberta — descoberta só faz
    IO (Vol.IV Cap.18, docstring de `descoberta_arquivos.py`)."""

    tipo: Literal["regex-agregado"] = "regex-agregado"
    caminho: str
    conteudo: str | None = None
    regra: RegraAgregadaSpec


class AchadoAgregado(BaseModel):
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


class SaidaAgregada(BaseModel):
    achados: list[AchadoAgregado] = Field(default_factory=list)


class EntradaInvalida(Exception):
    """Levantada quando `entrada` não satisfaz `EntradaAgregada` — vira
    SCHEMA_REJECTION no Execution Engine (Vol.III Cap.12)."""


def _computar_fingerprint(
    agente: str, categoria: str, caminho: str, codigo: str, chave: str = ""
) -> str:
    normalizado = caminho.replace("\\", "/")
    bruto = f"{agente}|{categoria}|{normalizado}|{codigo}|{chave}"
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()


def avaliar_regra_agregada(entrada: Any, contexto: ExecutionContext) -> Any:
    """Vol.IV Cap.17 — handler puro: recebe os arquivos já lidos pela
    camada de descoberta (empacotados como JSON em `conteudo`); parsing
    (não é IO) e concatenação acontecem aqui."""
    del contexto
    try:
        dados = EntradaAgregada.model_validate(entrada)
    except Exception as exc:
        raise EntradaInvalida(str(exc)) from exc

    payload = json.loads(dados.conteudo) if dados.conteudo else {}
    arquivos: dict[str, str] = payload.get("arquivos", {})

    regra = dados.regra
    flags = re.IGNORECASE if regra.ignore_case else 0
    combinado = "\n".join(arquivos.values())

    def _acha(pattern: str) -> bool:
        return re.search(pattern, combinado, flags) is not None

    if regra.modo == ModoAgregado.PRESENCA:
        disparado = _acha(regra.pattern)
    else:
        disparado = not _acha(regra.pattern)
        if regra.pattern_2 is not None:
            disparado = disparado or not _acha(regra.pattern_2)

    if not disparado:
        return SaidaAgregada(achados=[]).model_dump()

    fingerprint = _computar_fingerprint(
        regra.agente, regra.categoria, regra.caminho_relatado, regra.codigo
    )
    achado = AchadoAgregado(
        codigo=regra.codigo,
        agente=regra.agente,
        severidade=regra.severidade,
        categoria=regra.categoria,
        titulo=regra.titulo,
        descricao=f"{regra.caminho_relatado}: {regra.titulo}",
        causa=regra.causa,
        remediacao=regra.remediacao,
        arquivo=regra.caminho_relatado,
        fingerprint=fingerprint,
    )
    return SaidaAgregada(achados=[achado]).model_dump()


def construir_implementacao() -> CapabilityImplementation:
    definicao = CapabilityDefinition(
        id=CapabilityId("regex-agregado-multi-arquivo"),
        name="Regex agregado sobre multiplos arquivos",
        version="1.0.0",
        input_schema=EntradaAgregada.model_json_schema(),
        output_schema=SaidaAgregada.model_json_schema(),
        deterministic=True,
        side_effects=SideEffects.NONE,
        idempotent=True,
    )

    entrada_sucesso = {
        "caminho": "api",
        "conteudo": json.dumps({"arquivos": {"api/a.py": "sem o termo procurado aqui"}}),
        "regra": {
            "codigo": "TEST-AGR-001",
            "agente": "teste",
            "severidade": "high",
            "categoria": "teste",
            "titulo": "teste",
            "causa": "teste",
            "remediacao": "teste",
            "modo": "ausencia",
            "pattern": "termo_ausente_de_verdade",
            "caminho_relatado": "api",
        },
    }
    entrada_regex_malformado = {
        "caminho": "api",
        "conteudo": json.dumps({"arquivos": {"api/a.py": "x"}}),
        "regra": {
            "codigo": "TEST-AGR-002",
            "agente": "teste",
            "severidade": "high",
            "categoria": "teste",
            "titulo": "teste",
            "causa": "teste",
            "remediacao": "teste",
            "modo": "ausencia",
            "pattern": "(",
            "caminho_relatado": "api",
        },
    }

    return CapabilityImplementation(
        definition=definicao,
        handler=avaliar_regra_agregada,
        acceptance_tests=[
            AcceptanceTest(
                name="ausencia-agregada-dispara-um-achado",
                entrada=entrada_sucesso,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: len(saida["achados"]) == 1,
            ),
            AcceptanceTest(
                name="entrada-sem-campo-obrigatorio-e-rejeitada",
                entrada={"caminho": "api"},  # falta 'regra'
                resultado_esperado=ResultadoEsperado.SCHEMA_REJECTION,
            ),
            AcceptanceTest(
                name="pattern-malformado-e-tratado-como-falha-de-invocacao",
                entrada=entrada_regex_malformado,
                resultado_esperado=ResultadoEsperado.TIMEOUT,
            ),
        ],
    )
