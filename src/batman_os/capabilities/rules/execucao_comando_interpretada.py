"""Skill "executar comando externo, timeout, venv-aware" (Vol.IV Cap.17) —
Milestone 3, Skill 4.

Cobre as 6 regras que rodam um comando externo (pytest, ruff) e interpretam
o resultado: QA-RUN-001/002/003 (`Batman/scan/rules/robin.py`, roda pytest)
e ORA-001/002/003 (`Batman/scan/rules/oracle.py`, roda ruff). O `subprocess`
em si é executado por `cli/descoberta_arquivos.py` (tipo de descoberta
`"subprocess"`, com cache por comando+root — corrige uma ausência de cache
em `robin.py`, que rodava pytest uma vez por regra; `oracle.py` já cacheava
via `_ruff_cache`) — o handler aqui só INTERPRETA o resultado já empacotado
(`conteudo` é um JSON com `returncode`/`stdout`/`stderr`/metadados).

Um handler, 6 `interpretacao`s — cada uma replica o parsing específico de
uma regra legada (regex de resumo do pytest, filtro+agrupamento do JSON do
ruff). Diferente das outras Skills desta migração, aqui uma única invocação
pode gerar MÚLTIPLOS achados (`ORA-001`/`ORA-002` agrupam por arquivo/
símbolo) — `SaidaExecucaoComando.achados` já é uma lista por design, isso
não muda o contrato.
"""

from __future__ import annotations

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


class Interpretacao(StrEnum):
    PYTEST_FALHOU = "pytest_falhou"
    PYTEST_SEM_TESTES = "pytest_sem_testes"
    PYTEST_INDISPONIVEL = "pytest_indisponivel"
    RUFF_NOME_INDEFINIDO = "ruff_nome_indefinido"
    RUFF_IMPORT_NAO_USADO = "ruff_import_nao_usado"
    RUFF_INDISPONIVEL = "ruff_indisponivel"


class RegraExecucaoComandoSpec(BaseModel):
    codigo: str
    agente: str
    severidade: str
    categoria: str
    titulo: str
    causa: str
    remediacao: str
    interpretacao: Interpretacao


class EntradaExecucaoComando(BaseModel):
    tipo: Literal["execucao-comando-interpretada"] = "execucao-comando-interpretada"
    caminho: str
    conteudo: str | None = None
    regra: RegraExecucaoComandoSpec


class AchadoExecucaoComando(BaseModel):
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


class SaidaExecucaoComando(BaseModel):
    achados: list[AchadoExecucaoComando] = Field(default_factory=list)


class EntradaInvalida(Exception):
    """Levantada quando `entrada` não satisfaz `EntradaExecucaoComando` —
    vira SCHEMA_REJECTION no Execution Engine (Vol.III Cap.12)."""


class _Resultado(BaseModel):
    """Formato empacotado por `cli/descoberta_arquivos.py` (tipo de
    descoberta `"subprocess"`) em `EntradaExecucaoComando.conteudo`."""

    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    dir_requerido_existe: bool | None = None
    arquivos_teste_encontrados: list[str] = Field(default_factory=list)


def _computar_fingerprint(
    agente: str, categoria: str, caminho: str, codigo: str, chave: str
) -> str:
    import hashlib

    normalizado = caminho.replace("\\", "/")
    bruto = f"{agente}|{categoria}|{normalizado}|{codigo}|{chave}"
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()


def _achado(
    regra: RegraExecucaoComandoSpec,
    caminho: str,
    descricao: str,
    chave: str = "",
    *,
    severidade: str | None = None,
) -> AchadoExecucaoComando:
    fingerprint = _computar_fingerprint(regra.agente, regra.categoria, caminho, regra.codigo, chave)
    return AchadoExecucaoComando(
        codigo=regra.codigo,
        agente=regra.agente,
        severidade=severidade or regra.severidade,
        categoria=regra.categoria,
        titulo=regra.titulo,
        descricao=descricao,
        causa=regra.causa,
        remediacao=regra.remediacao,
        arquivo=caminho,
        chave=chave,
        fingerprint=fingerprint,
    )


_CHAVE_TIMEOUT_SCANNER = "timeout-do-scanner"


def _parse_resumo_pytest(stdout: str) -> tuple[int, int, int]:
    falhas = passou = erros = 0
    m = re.search(r"(\d+) failed", stdout)
    if m:
        falhas = int(m.group(1))
    m = re.search(r"(\d+) passed", stdout)
    if m:
        passou = int(m.group(1))
    m = re.search(r"(\d+) error", stdout)
    if m:
        erros = int(m.group(1))
    return falhas, passou, erros


def _extrair_nomes_falhos(stdout: str, limite: int = 5) -> list[str]:
    nomes: list[str] = []
    for linha in stdout.splitlines():
        m = re.match(r"^FAILED\s+(.+)", linha.strip())
        if m:
            nomes.append(m.group(1).strip())
        if len(nomes) >= limite:
            break
    return nomes


def _achado_timeout_scanner(
    regra: RegraExecucaoComandoSpec, caminho: str, r: _Resultado, *, comando: str
) -> AchadoExecucaoComando:
    """Achado PRÓPRIO para o sentinela de timeout (-2) de
    `descoberta_arquivos.py::_rodar_subprocess_cacheado` — SEMPRE severidade
    `low` e SEMPRE uma `chave`/descrição distintas de "suite quebrada" ou
    "comando indisponível", nunca reaproveita `regra.severidade` (achado
    real: QA-RUN-001 flagrava HIGH — "suite de testes quebrada" — numa
    suite que passa 100% rodada direto, só mais lenta que o timeout interno
    do scanner; o mesmo bug existia em ORA-003/`ruff falhou` para timeout do
    ruff). Timeout do SCANNER (que tem um teto interno para não travar o
    scan inteiro) não é evidência de o comando ter falhado de verdade —
    é evidência de o comando ser lento demais para ESTE scanner."""
    return _achado(
        regra,
        caminho,
        f"{comando} excedeu o timeout do scanner ({r.stderr}) — comando lento demais para "
        f"o scanner, NAO necessariamente quebrado/indisponível (rode '{comando}' localmente "
        "sem o teto de tempo do scanner para confirmar o resultado real)",
        _CHAVE_TIMEOUT_SCANNER,
        severidade="low",
    )


def _interpretar_pytest_falhou(
    regra: RegraExecucaoComandoSpec, caminho: str, r: _Resultado
) -> list[AchadoExecucaoComando]:
    if r.dir_requerido_existe is False:
        return []
    if r.returncode == -2:
        return [_achado_timeout_scanner(regra, caminho, r, comando="pytest")]
    if r.returncode in (None, -1, 0, 5):
        return []
    falhas, passou, erros = _parse_resumo_pytest(r.stdout)
    nomes = _extrair_nomes_falhos(r.stdout)
    resumo = f"{falhas} falha(s), {erros} erro(s), {passou} ok"
    nomes_str = "; ".join(nomes) if nomes else "(ver output completo)"
    descricao = f"pytest retornou exit {r.returncode}: {resumo}. Testes: {nomes_str}"
    chave = "|".join(sorted(nomes)) if nomes else f"pytest-rc{r.returncode}"
    return [_achado(regra, caminho, descricao, chave)]


def _interpretar_pytest_sem_testes(
    regra: RegraExecucaoComandoSpec, caminho: str, r: _Resultado
) -> list[AchadoExecucaoComando]:
    if r.dir_requerido_existe is False:
        return [_achado(regra, caminho, "Diretório tests/ não encontrado", "no-tests-dir")]
    if not r.arquivos_teste_encontrados:
        return [
            _achado(
                regra, caminho, "tests/ existe mas não contém arquivos test_*.py", "no-test-files"
            )
        ]
    if r.returncode == 5:
        qtd = len(r.arquivos_teste_encontrados)
        descricao = f"{qtd} arquivo(s) encontrado(s) mas pytest não coletou nenhum teste"
        return [_achado(regra, caminho, descricao, "pytest-nothing-collected")]
    return []


def _interpretar_pytest_indisponivel(
    regra: RegraExecucaoComandoSpec, caminho: str, r: _Resultado
) -> list[AchadoExecucaoComando]:
    if r.returncode == -1:
        return [_achado(regra, caminho, f"pytest não encontrado: {r.stderr}", "pytest-not-found")]
    return []


def _ruff_items(r: _Resultado) -> list[dict[str, Any]]:
    if r.returncode != 0:
        return []
    try:
        itens: list[dict[str, Any]] = json.loads(r.stdout or "[]")
    except json.JSONDecodeError:
        return []
    return itens


def _interpretar_ruff_nome_indefinido(
    regra: RegraExecucaoComandoSpec, caminho: str, r: _Resultado
) -> list[AchadoExecucaoComando]:
    if r.returncode != 0:
        return []
    grupos: dict[tuple[str, str], list[int]] = {}
    for item in _ruff_items(r):
        codigo = item.get("code") or ""
        if codigo != "F821" and not codigo.startswith("E9"):
            continue
        rel = item.get("filename", "")
        msg = item.get("message", "")
        m = re.search(r"`([^`]+)`", msg)
        simbolo = m.group(1) if m else codigo
        linha = (item.get("location") or {}).get("row", 0)
        grupos.setdefault((rel, simbolo), []).append(linha)

    achados = []
    for (rel, simbolo), linhas in sorted(grupos.items()):
        linhas_str = ",".join(str(linha) for linha in sorted(linhas))
        descricao = f"{rel}: `{simbolo}` indefinido (linha(s) {linhas_str})"
        achados.append(_achado(regra, rel, descricao, simbolo))
    return achados


def _interpretar_ruff_import_nao_usado(
    regra: RegraExecucaoComandoSpec, caminho: str, r: _Resultado
) -> list[AchadoExecucaoComando]:
    if r.returncode != 0:
        return []
    grupos: dict[str, list[str]] = {}
    for item in _ruff_items(r):
        if (item.get("code") or "") != "F401":
            continue
        rel = item.get("filename", "")
        m = re.search(r"`([^`]+)`", item.get("message", ""))
        simbolo = m.group(1) if m else "?"
        linha = (item.get("location") or {}).get("row", 0)
        grupos.setdefault(rel, []).append(f"{simbolo} (l.{linha})")

    achados = []
    for rel, simbolos in sorted(grupos.items()):
        mostrados = "; ".join(simbolos[:5])
        extra = f" (+{len(simbolos) - 5})" if len(simbolos) > 5 else ""
        descricao = f"{rel}: {len(simbolos)} import(s) sem uso — {mostrados}{extra}"
        achados.append(_achado(regra, rel, descricao))
    return achados


def _interpretar_ruff_indisponivel(
    regra: RegraExecucaoComandoSpec, caminho: str, r: _Resultado
) -> list[AchadoExecucaoComando]:
    if r.returncode == -2:
        return [_achado_timeout_scanner(regra, caminho, r, comando="ruff")]
    if r.returncode != 0:
        descricao = f"ruff falhou (rc={r.returncode}): {r.stderr}"
        return [_achado(regra, caminho, descricao, "ruff-error")]
    return []


_DISPATCH = {
    Interpretacao.PYTEST_FALHOU: _interpretar_pytest_falhou,
    Interpretacao.PYTEST_SEM_TESTES: _interpretar_pytest_sem_testes,
    Interpretacao.PYTEST_INDISPONIVEL: _interpretar_pytest_indisponivel,
    Interpretacao.RUFF_NOME_INDEFINIDO: _interpretar_ruff_nome_indefinido,
    Interpretacao.RUFF_IMPORT_NAO_USADO: _interpretar_ruff_import_nao_usado,
    Interpretacao.RUFF_INDISPONIVEL: _interpretar_ruff_indisponivel,
}


def avaliar_regra_execucao_comando(entrada: Any, contexto: ExecutionContext) -> Any:
    del contexto
    try:
        dados = EntradaExecucaoComando.model_validate(entrada)
    except Exception as exc:
        raise EntradaInvalida(str(exc)) from exc

    if dados.conteudo is None:
        return SaidaExecucaoComando(achados=[]).model_dump()

    try:
        resultado = _Resultado.model_validate(json.loads(dados.conteudo))
    except Exception:
        return SaidaExecucaoComando(achados=[]).model_dump()

    interprete = _DISPATCH[dados.regra.interpretacao]
    achados = interprete(dados.regra, dados.caminho, resultado)
    return SaidaExecucaoComando(achados=achados).model_dump()


def construir_implementacao() -> CapabilityImplementation:
    definicao = CapabilityDefinition(
        id=CapabilityId("execucao-comando-interpretada"),
        name="Execucao de comando externo interpretada (pytest/ruff)",
        version="1.0.0",
        input_schema=EntradaExecucaoComando.model_json_schema(),
        output_schema=SaidaExecucaoComando.model_json_schema(),
        deterministic=True,
        side_effects=SideEffects.NONE,
        idempotent=True,
    )

    regra_teste = {
        "codigo": "TEST-EXEC-001",
        "agente": "teste",
        "severidade": "high",
        "categoria": "teste",
        "titulo": "teste",
        "causa": "teste",
        "remediacao": "teste",
        "interpretacao": "pytest_falhou",
    }
    entrada_sucesso = {
        "caminho": "tests/",
        "conteudo": json.dumps(
            {
                "returncode": 1,
                "stdout": "1 failed, 2 passed",
                "stderr": "",
                "dir_requerido_existe": True,
            }
        ),
        "regra": regra_teste,
    }
    entrada_conteudo_malformado = {
        "caminho": "tests/",
        "conteudo": "isto nao e json valido",
        "regra": regra_teste,
    }
    entrada_regra_invalida = {
        "caminho": "tests/",
        "conteudo": json.dumps({"returncode": 1, "stdout": "", "stderr": ""}),
        "regra": {**regra_teste, "interpretacao": "nao-existe"},
    }

    return CapabilityImplementation(
        definition=definicao,
        handler=avaliar_regra_execucao_comando,
        acceptance_tests=[
            AcceptanceTest(
                name="pytest-falhou-dispara",
                entrada=entrada_sucesso,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: len(saida["achados"]) == 1,
            ),
            AcceptanceTest(
                name="entrada-sem-campo-obrigatorio-e-rejeitada",
                entrada={"caminho": "tests/"},
                resultado_esperado=ResultadoEsperado.SCHEMA_REJECTION,
            ),
            AcceptanceTest(
                name="conteudo-json-malformado-nao-quebra-o-handler",
                entrada=entrada_conteudo_malformado,
                resultado_esperado=ResultadoEsperado.SUCCESS,
                matcher_saida=lambda saida: saida["achados"] == [],
            ),
            AcceptanceTest(
                name="interpretacao_desconhecida_e_tratada_como_falha_de_invocacao",
                entrada=entrada_regra_invalida,
                resultado_esperado=ResultadoEsperado.TIMEOUT,
            ),
        ],
    )
