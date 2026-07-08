"""Capability genérica "regex sobre conteúdo de arquivo" (Vol.IV Cap.16).

Migração do primeiro lote de regras do Batman atual (`radar-preditivo/Batman/
scan/rules/*.py`) — cobre as 5 formas de condição encontradas nas 14 regras
candidatas do primeiro lote: presença de padrão, ausência de padrão, arquivo
ausente, arquivo presente, presença sem mitigação. `condicoes_adicionais`
(avaliadas em AND com a condição principal) cobrem as regras com checagem
cruzada entre 2+ arquivos (DEVOPS-003, DE-002, CLOUD-007).

Handler puro sobre texto já carregado — quem lê do disco é o CLI
(`cli/descoberta_arquivos.py`), não esta Capability (evita inventar Tool/
Skill de filesystem prematuramente, Vol.IV Cap.18).

`Achado.fingerprint` replica exatamente `Batman/scan/schema.py::Finding.
compute_fingerprint()` (sha1 de `agente|categoria|caminho|codigo|chave`,
caminho normalizado com `\\`->`/`) — permite comparação byte-a-byte com o
motor legado (`scripts/compare_migracao.py`).
"""

from __future__ import annotations

import hashlib
import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from batman_os.capabilities.capability_contract import (
    AcceptanceTest,
    CapabilityImplementation,
    ResultadoEsperado,
)
from batman_os.capabilities.operator import ExecutionContext
from batman_os.foundation.types import CapabilityId
from batman_os.runtime.capability_engine import CapabilityDefinition, SideEffects


class ModoAvaliacao(StrEnum):
    """As 5 formas de condição encontradas no primeiro lote de 14 regras
    migradas do Batman atual (ver plano de migração)."""

    PRESENCA = "presenca"
    AUSENCIA = "ausencia"
    ARQUIVO_AUSENTE = "arquivo-ausente"
    ARQUIVO_PRESENTE = "arquivo-presente"
    PRESENCA_SEM_MITIGACAO = "presenca-sem-mitigacao"


class CondicaoAdicional(BaseModel):
    """Condição extra avaliada em AND com a condição principal de
    `RegraSpec` — cobre regras com checagem cruzada entre 2+ arquivos
    (DEVOPS-003: `.env` presente E `.gitignore` sem `.env`; DE-002: nenhum
    de 3 caminhos candidatos existe; CLOUD-007: algum Dockerfile existe E
    `.dockerignore` ausente). Só suporta os 4 modos "simples" (não
    `presenca-sem-mitigacao`, que só faz sentido como condição principal)."""

    caminho: str
    conteudo: str | None = None
    checar: ModoAvaliacao
    pattern: str | None = None
    ignore_case: bool = False


class RegraSpec(BaseModel):
    """Espelha o formato de `PatternRule` do Batman atual (`Batman/scan/
    pattern_rule.py`) — os mesmos campos de julgamento embutido (causa/
    remediacao) que `Rule` carrega hoje como atributos de classe.

    `pattern_nome_arquivo_incluir`/`pattern_caminho_incluir` (achado da
    continuação da migração — LEGAL-004/PD-003/RISK-005/UXR-005): filtro
    de INCLUSÃO por nome de arquivo ou caminho relativo completo — a
    camada de descoberta (`descoberta_arquivos.py`) só suporta EXCLUSÃO
    por substring; esses códigos precisam do inverso ("só processa
    arquivos cujo nome/caminho contém X"), então o filtro roda aqui, no
    handler, sobre `dados.caminho` — sem precisar estender a camada de
    descoberta genérica para um caso que só esses códigos usam."""

    codigo: str
    agente: str
    severidade: str
    categoria: str
    titulo: str
    causa: str
    remediacao: str
    modo: ModoAvaliacao
    pattern: str | None = None
    pattern_mitigacao: str | None = None
    pattern_escopo: str | None = None
    pattern_nome_arquivo_incluir: str | None = None
    pattern_caminho_incluir: str | None = None
    ignore_case: bool = False


class EntradaRegexArquivo(BaseModel):
    """Vol.IV Cap.16 — payload de entrada do handler. `conteudo=None`
    significa "arquivo não existe no disco" (distinto de arquivo vazio,
    `conteudo=""`)."""

    caminho: str
    conteudo: str | None = None
    condicoes_adicionais: list[CondicaoAdicional] = Field(default_factory=list)
    regra: RegraSpec


class Achado(BaseModel):
    """Espelha `Batman/scan/schema.py::Finding` — mesmos campos de
    julgamento embutido, para permitir comparação direta com o motor
    legado."""

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


class SaidaRegexArquivo(BaseModel):
    achados: list[Achado] = Field(default_factory=list)


class EntradaInvalida(Exception):
    """Levantada quando `entrada` não satisfaz `EntradaRegexArquivo` —
    o Execution Engine (Vol.III Cap.12) trata qualquer exceção do handler
    como falha de invocação, cobrindo a categoria SCHEMA_REJECTION do
    checklist de certificação (Vol.IV Cap.16, secao 16.3)."""


def _computar_fingerprint(
    agente: str, categoria: str, caminho: str, codigo: str, chave: str = ""
) -> str:
    """Replica exatamente `Batman/scan/schema.py::Finding.
    compute_fingerprint()` — permite comparação byte-a-byte com o motor
    legado (`scripts/compare_migracao.py`)."""
    normalizado = caminho.replace("\\", "/")
    bruto = f"{agente}|{categoria}|{normalizado}|{codigo}|{chave}"
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()


def _condicao_simples_satisfeita(
    conteudo: str | None, modo: ModoAvaliacao, pattern: str | None, ignore_case: bool
) -> bool:
    """Avalia os 4 modos "simples" (tudo exceto `presenca-sem-mitigacao`,
    que tem lógica própria em `avaliar_regra_regex` por combinar 2
    patterns)."""
    flags = re.IGNORECASE if ignore_case else 0

    if modo == ModoAvaliacao.ARQUIVO_PRESENTE:
        return conteudo is not None
    if modo == ModoAvaliacao.ARQUIVO_AUSENTE:
        return conteudo is None
    if modo == ModoAvaliacao.PRESENCA:
        if conteudo is None or not pattern:
            return False
        return re.search(pattern, conteudo, flags) is not None
    if modo == ModoAvaliacao.AUSENCIA:
        if conteudo is None:
            # Arquivo ausente -> nao ha conteudo para confirmar a ausencia do
            # padrao (ex.: VPS-002 exige que .env.production.example exista
            # antes de checar ENABLE_REAL_TRADING=false — arquivo ausente e
            # responsabilidade de outra regra, VPS-001). Quando "arquivo
            # ausente" deve CONTAR como "protecao ausente" (ex.: DEVOPS-003:
            # .gitignore inexistente tambem nao protege .env), a camada de
            # descoberta (`cli/descoberta_arquivos.py`) passa `conteudo=""`
            # em vez de `None` para essa condicao especifica — decisao de
            # preparo de dado, nao deste handler.
            return False
        if not pattern:
            return True
        return re.search(pattern, conteudo, flags) is None
    raise ValueError(
        f"modo '{modo}' so e valido como condicao principal, nao em condicoes_adicionais"
    )


def avaliar_regra_regex(entrada: Any, contexto: ExecutionContext) -> Any:
    """Vol.IV Cap.16 — handler puro: nenhum IO, só avalia o `conteudo` já
    carregado contra a `RegraSpec`. `contexto` não influencia a lógica (a
    Capability é read-only e determinística) — presente só para satisfazer
    a assinatura exigida por `CapabilityImplementation.handler`."""
    del contexto
    try:
        dados = EntradaRegexArquivo.model_validate(entrada)
    except Exception as exc:
        raise EntradaInvalida(str(exc)) from exc

    regra = dados.regra
    ic = regra.ignore_case
    flags = re.IGNORECASE if ic else 0

    if regra.pattern_nome_arquivo_incluir or regra.pattern_caminho_incluir:
        nome_arquivo = dados.caminho.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        if regra.pattern_nome_arquivo_incluir and not re.search(
            regra.pattern_nome_arquivo_incluir, nome_arquivo, flags
        ):
            return SaidaRegexArquivo(achados=[]).model_dump()
        if regra.pattern_caminho_incluir and not re.search(
            regra.pattern_caminho_incluir, dados.caminho, flags
        ):
            return SaidaRegexArquivo(achados=[]).model_dump()

    if regra.modo == ModoAvaliacao.PRESENCA_SEM_MITIGACAO:
        if dados.conteudo is None or not regra.pattern:
            disparado = False
        else:
            tem_padrao = re.search(regra.pattern, dados.conteudo, flags) is not None
            tem_mitigacao = bool(
                regra.pattern_mitigacao
                and re.search(regra.pattern_mitigacao, dados.conteudo, flags) is not None
            )
            disparado = tem_padrao and not tem_mitigacao
    elif regra.modo == ModoAvaliacao.AUSENCIA and regra.pattern_escopo:
        # gating: so avalia a ausencia se o padrao de escopo estiver
        # presente (ex.: NS-002 - so exige HSTS em blocos que ja tem
        # ssl_certificate).
        if dados.conteudo is None:
            disparado = False
        else:
            em_escopo = re.search(regra.pattern_escopo, dados.conteudo, flags) is not None
            disparado = em_escopo and _condicao_simples_satisfeita(
                dados.conteudo, ModoAvaliacao.AUSENCIA, regra.pattern, ic
            )
    else:
        disparado = _condicao_simples_satisfeita(dados.conteudo, regra.modo, regra.pattern, ic)

    if disparado:
        for condicao in dados.condicoes_adicionais:
            if not _condicao_simples_satisfeita(
                condicao.conteudo, condicao.checar, condicao.pattern, condicao.ignore_case
            ):
                disparado = False
                break

    if not disparado:
        return SaidaRegexArquivo(achados=[]).model_dump()

    fingerprint = _computar_fingerprint(regra.agente, regra.categoria, dados.caminho, regra.codigo)
    achado = Achado(
        codigo=regra.codigo,
        agente=regra.agente,
        severidade=regra.severidade,
        categoria=regra.categoria,
        titulo=regra.titulo,
        descricao=f"{dados.caminho}: {regra.titulo}",
        causa=regra.causa,
        remediacao=regra.remediacao,
        arquivo=dados.caminho,
        fingerprint=fingerprint,
    )
    return SaidaRegexArquivo(achados=[achado]).model_dump()


def construir_implementacao() -> CapabilityImplementation:
    """Vol.IV Cap.16, secao 16.3 — monta a `CapabilityImplementation` pronta
    para `certificar()`."""
    definicao = CapabilityDefinition(
        id=CapabilityId("regex-sobre-conteudo-de-arquivo"),
        name="Regex sobre conteudo de arquivo",
        version="1.0.0",
        input_schema=EntradaRegexArquivo.model_json_schema(),
        output_schema=SaidaRegexArquivo.model_json_schema(),
        deterministic=True,
        side_effects=SideEffects.NONE,
        idempotent=True,
    )

    entrada_sucesso = {
        "caminho": "app.py",
        "conteudo": "SECRET_KEY = 'abc123'",
        "regra": {
            "codigo": "TEST-001",
            "agente": "teste",
            "severidade": "high",
            "categoria": "teste",
            "titulo": "teste",
            "causa": "teste",
            "remediacao": "teste",
            "modo": "presenca",
            "pattern": "SECRET_KEY",
        },
    }
    entrada_pattern_invalido = {
        "caminho": "app.py",
        "conteudo": "x",
        "regra": {
            "codigo": "TEST-002",
            "agente": "teste",
            "severidade": "high",
            "categoria": "teste",
            "titulo": "teste",
            "causa": "teste",
            "remediacao": "teste",
            "modo": "presenca",
            "pattern": "(",  # regex malformado -> re.error, tratado como falha de invocacao
        },
    }

    return CapabilityImplementation(
        definition=definicao,
        handler=avaliar_regra_regex,
        acceptance_tests=[
            AcceptanceTest(
                name="regra-de-presenca-dispara-achado",
                entrada=entrada_sucesso,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: len(saida["achados"]) == 1,
            ),
            AcceptanceTest(
                name="entrada-sem-campo-obrigatorio-e-rejeitada",
                entrada={"caminho": "app.py"},  # falta 'regra'
                resultado_esperado=ResultadoEsperado.SCHEMA_REJECTION,
            ),
            AcceptanceTest(
                name="pattern-malformado-e-tratado-como-falha-de-invocacao",
                entrada=entrada_pattern_invalido,
                resultado_esperado=ResultadoEsperado.TIMEOUT,
            ),
        ],
    )
