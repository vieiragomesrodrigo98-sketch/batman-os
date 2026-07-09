"""Descoberta de arquivos no repositório alvo — único ponto de IO real desta
migração (Vol.IV Cap.18: nenhuma Skill/Tool de filesystem foi modelada ainda,
então este módulo lê do disco diretamente em vez de inventar uma abstração
prematura).

Interpreta a seção `descoberta` dos specs em `capabilities/rules/specs/
lote_01/*.json` — 7 tipos: `arquivo_fixo` (um caminho único), `arvore`
(busca recursiva por extensão sob `scope_dirs`), `glob` (padrões glob
relativos à raiz, ou um único padrão recursivo com exclusões), `git` (roda
um comando `git` fixo uma vez, replicando `RepoContext.git()` do legado),
`subprocess` (roda um módulo Python instalado no venv do repo alvo —
pytest/ruff — com cache por comando+root dentro da mesma execução de
`executar_scan`, replicando/corrigindo `_find_python()` + `_ruff_cache`/
ausência de cache de `oracle.py`/`robin.py`), `toml_dependencias` (empacota
`pyproject.toml` + `requirements.txt` + arquivos `.py` de `tests/`/`src/`
como JSON — parsing real via `tomllib` acontece no handler, não aqui),
`de003` (bespoke — empacota `init_db.py`/`tables.py` + `git log -p` sobre
`tables.py` como JSON para a Capability DE-003), `ora004` (bespoke —
empacota todos os `.py` de `scope_dirs` + `enums_path` como JSON para a
Capability ORA-004, que agrega frequência de literais através de TODOS os
arquivos).

Handler da Capability (`capabilities/rules/regex_sobre_conteudo.py`, e as
demais Skills desta migração) permanece puro — este módulo é o único que
toca disco/processo.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from batman_os.capabilities.rules.a11y002_onclick_sem_teclado import (
    EntradaA11y002,
    RegraA11y002Spec,
)
from batman_os.capabilities.rules.a11y003_input_sem_label import EntradaA11y003, RegraA11y003Spec
from batman_os.capabilities.rules.arch003_pagina_orfa import EntradaArch003, RegraArch003Spec
from batman_os.capabilities.rules.ast_kwarg_ausente import (
    EntradaKwargAusente,
    RegraKwargAusenteSpec,
)
from batman_os.capabilities.rules.ast_padrao_ausente import EntradaAst, RegraAstSpec
from batman_os.capabilities.rules.ba004_logica_negocio_router import EntradaBa004, RegraBa004Spec
from batman_os.capabilities.rules.ba005_divisao_sem_guarda import EntradaBa005, RegraBa005Spec
from batman_os.capabilities.rules.be010_dependencia_nao_declarada import (
    EntradaBe010,
    RegraBe010Spec,
)
from batman_os.capabilities.rules.be013_http200_em_except import EntradaBe013, RegraBe013Spec
from batman_os.capabilities.rules.cs003_except_pass import EntradaCs003, RegraCs003Spec
from batman_os.capabilities.rules.cs005_erro_sem_request_id import EntradaCs005, RegraCs005Spec
from batman_os.capabilities.rules.cto002_rota_sem_versao import EntradaCto002, RegraCto002Spec
from batman_os.capabilities.rules.cto004_endpoint_sem_doc import EntradaCto004, RegraCto004Spec
from batman_os.capabilities.rules.de003_coluna_sem_migration import EntradaDe003, RegraDe003Spec
from batman_os.capabilities.rules.doc004_changelog_sem_versao import EntradaDoc004, RegraDoc004Spec
from batman_os.capabilities.rules.execucao_comando_interpretada import (
    EntradaExecucaoComando,
    RegraExecucaoComandoSpec,
)
from batman_os.capabilities.rules.fe001_export_duplicado import EntradaFe001, RegraFe001Spec
from batman_os.capabilities.rules.feapi_rota_sem_frontend import EntradaFeApi, RegraFeApiSpec
from batman_os.capabilities.rules.fin005_backtest_sem_oos import EntradaFin005, RegraFin005Spec
from batman_os.capabilities.rules.git_comando_interpretado import (
    EntradaGitInterpretado,
    RegraComparacaoNumericaSpec,
)
from batman_os.capabilities.rules.govdebt001_finding_sem_decisao import (
    EntradaGovdebt001,
    RegraGovdebt001Spec,
)
from batman_os.capabilities.rules.janela_contexto_regex import EntradaJanela, RegraJanelaSpec
from batman_os.capabilities.rules.metrica_com_limiar import EntradaMetrica, RegraMetricaSpec
from batman_os.capabilities.rules.ora004_status_typo import EntradaOra004, RegraOra004Spec
from batman_os.capabilities.rules.ora005_fallback_silencioso import EntradaOra005, RegraOra005Spec
from batman_os.capabilities.rules.pd001_empty_state_sem_cta import EntradaPd001, RegraPd001Spec
from batman_os.capabilities.rules.pd009_rota_nao_descobrivel import EntradaPd009, RegraPd009Spec
from batman_os.capabilities.rules.pd010_simulador_sem_piso import EntradaPd010, RegraPd010Spec
from batman_os.capabilities.rules.pd011_diversificacao_nao_comunicada import (
    EntradaPd011,
    RegraPd011Spec,
)
from batman_os.capabilities.rules.perf004_arquivo_sem_streaming import (
    EntradaPerf004,
    RegraPerf004Spec,
)
from batman_os.capabilities.rules.qaauto001_router_sem_teste import (
    EntradaQaAuto001,
    RegraQaAuto001Spec,
)
from batman_os.capabilities.rules.qaauto003_smoke_specs_ausentes import (
    EntradaQaAuto003,
    RegraQaAuto003Spec,
)
from batman_os.capabilities.rules.regex_agregado_multi_arquivo import (
    EntradaAgregada,
    RegraAgregadaSpec,
)
from batman_os.capabilities.rules.regex_sobre_conteudo import (
    CondicaoAdicional,
    EntradaRegexArquivo,
    ModoAvaliacao,
    RegraSpec,
)
from batman_os.capabilities.rules.rev006_variavel_nome_curto import EntradaRev006, RegraRev006Spec
from batman_os.capabilities.rules.sec005_fstring_sql import EntradaSec005, RegraSec005Spec
from batman_os.capabilities.rules.sec007_ddl_no_import import EntradaSec007, RegraSec007Spec
from batman_os.capabilities.rules.sec008_role_sem_super_admin import EntradaSec008, RegraSec008Spec
from batman_os.capabilities.rules.sec009_admin_role_script import EntradaSec009, RegraSec009Spec
from batman_os.capabilities.rules.sre006_timeout_ausente import EntradaSre006, RegraSre006Spec
from batman_os.capabilities.rules.sup001_excecao_silenciada import (
    EntradaSup001,
    RegraSup001Spec,
)
from batman_os.capabilities.rules.sweep001_cadencia_quebrada import (
    EntradaSweep001,
    RegraSweep001Spec,
)
from batman_os.capabilities.rules.toml_dependencias import (
    EntradaDependencias,
    RegraDependenciasSpec,
)
from batman_os.capabilities.rules.ui002_inline_style_estatico import EntradaUi002, RegraUi002Spec

_cache_subprocess: dict[tuple[str, ...], tuple[int, str, str]] = {}


class TipoDescobertaDesconhecido(Exception):
    """Levantada quando `descoberta["tipo"]` (ou o `tipo` de uma condição
    adicional) não é um dos reconhecidos por este módulo."""


def entradas_cto004_para_regra(
    root: Path, regra: RegraCto004Spec, descoberta: dict[str, Any]
) -> list[EntradaCto004]:
    """Mesmo espírito de `entradas_a11y003_para_regra`, para a Capability
    bespoke CTO-004 — reaproveita a descoberta genérica `"arvore"`."""
    return [
        EntradaCto004(caminho=caminho, conteudo=conteudo, regra=regra)
        for caminho, conteudo in arquivos_para_regra(root, descoberta)
    ]


def entradas_cto002_para_regra(
    root: Path, regra: RegraCto002Spec, descoberta: dict[str, Any]
) -> list[EntradaCto002]:
    """Mesmo espírito de `entradas_a11y003_para_regra`, para a Capability
    bespoke CTO-002 — reaproveita a descoberta genérica `"arvore"`."""
    return [
        EntradaCto002(caminho=caminho, conteudo=conteudo, regra=regra)
        for caminho, conteudo in arquivos_para_regra(root, descoberta)
    ]


def entradas_cs005_para_regra(
    root: Path, regra: RegraCs005Spec, descoberta: dict[str, Any]
) -> list[EntradaCs005]:
    """Mesmo espírito de `entradas_a11y003_para_regra`, para a Capability
    bespoke CS-005."""
    return [
        EntradaCs005(caminho=caminho, conteudo=conteudo, regra=regra)
        for caminho, conteudo in arquivos_para_regra(root, descoberta)
    ]


def entradas_cs003_para_regra(
    root: Path, regra: RegraCs003Spec, descoberta: dict[str, Any]
) -> list[EntradaCs003]:
    """Mesmo espírito de `entradas_a11y003_para_regra`, para a Capability
    bespoke CS-003 — reaproveita a descoberta genérica `"arvore"`."""
    return [
        EntradaCs003(caminho=caminho, conteudo=conteudo, regra=regra)
        for caminho, conteudo in arquivos_para_regra(root, descoberta)
    ]


def entradas_ui002_para_regra(
    root: Path, regra: RegraUi002Spec, descoberta: dict[str, Any]
) -> list[EntradaUi002]:
    """Mesmo espírito de `entradas_a11y003_para_regra`, para a Capability
    bespoke UI-002 — reaproveita a descoberta genérica `"arvore"`."""
    return [
        EntradaUi002(caminho=caminho, conteudo=conteudo, regra=regra)
        for caminho, conteudo in arquivos_para_regra(root, descoberta)
    ]


def entradas_a11y002_para_regra(
    root: Path, regra: RegraA11y002Spec, descoberta: dict[str, Any]
) -> list[EntradaA11y002]:
    """Mesmo espírito de `entradas_a11y003_para_regra`, para a Capability
    bespoke A11Y-002 — reaproveita a descoberta genérica `"arvore"`."""
    return [
        EntradaA11y002(caminho=caminho, conteudo=conteudo, regra=regra)
        for caminho, conteudo in arquivos_para_regra(root, descoberta)
    ]


def entradas_a11y003_para_regra(
    root: Path, regra: RegraA11y003Spec, descoberta: dict[str, Any]
) -> list[EntradaA11y003]:
    """Mesmo espírito de `entradas_ast_para_regra`, para a Capability
    bespoke A11Y-003 — reaproveita a descoberta genérica `"arvore"` já
    existente (nenhuma função de descoberta nova precisa)."""
    return [
        EntradaA11y003(caminho=caminho, conteudo=conteudo, regra=regra)
        for caminho, conteudo in arquivos_para_regra(root, descoberta)
    ]


def entradas_govdebt001_para_regra(
    root: Path, regra: RegraGovdebt001Spec, descoberta: dict[str, Any]
) -> list[EntradaGovdebt001]:
    """Mesmo espírito de `entradas_a11y003_para_regra`, para a Capability
    bespoke GOVDEBT-001."""
    return [
        EntradaGovdebt001(caminho=caminho, conteudo=conteudo, regra=regra)
        for caminho, conteudo in arquivos_para_regra(root, descoberta)
    ]


def entradas_sweep001_para_regra(
    root: Path, regra: RegraSweep001Spec, descoberta: dict[str, Any]
) -> list[EntradaSweep001]:
    """Mesmo espírito de `entradas_a11y003_para_regra`, para a Capability
    bespoke SWEEP-001 — reaproveita a descoberta genérica
    `"arquivo_fixo"`."""
    return [
        EntradaSweep001(caminho=caminho, conteudo=conteudo, regra=regra)
        for caminho, conteudo in arquivos_para_regra(root, descoberta)
    ]


def entradas_para_regra(
    root: Path, regra: RegraSpec, descoberta: dict[str, Any]
) -> list[EntradaRegexArquivo]:
    """Monta as `EntradaRegexArquivo` prontas para invocar a Capability —
    uma por arquivo relevante encontrado, todas compartilhando as mesmas
    `condicoes_adicionais` (resolvidas uma única vez)."""
    condicoes = _condicoes_adicionais_para(root, descoberta)
    return [
        EntradaRegexArquivo(
            caminho=caminho, conteudo=conteudo, condicoes_adicionais=condicoes, regra=regra
        )
        for caminho, conteudo in arquivos_para_regra(root, descoberta)
    ]


def entradas_ast_para_regra(
    root: Path, regra: RegraAstSpec, descoberta: dict[str, Any]
) -> list[EntradaAst]:
    """Mesmo espírito de `entradas_para_regra`, para a Skill AST — sem
    `condicoes_adicionais` (nenhuma regra migrada até agora precisa de
    checagem cruzada entre arquivos nesta Skill)."""
    return [
        EntradaAst(caminho=caminho, conteudo=conteudo, regra=regra)
        for caminho, conteudo in arquivos_para_regra(root, descoberta)
    ]


def entradas_kwarg_ausente_para_regra(
    root: Path, regra: RegraKwargAusenteSpec, descoberta: dict[str, Any]
) -> list[EntradaKwargAusente]:
    """Mesmo espírito de `entradas_ast_para_regra`, para a Skill "Call com
    kwarg obrigatório ausente"."""
    return [
        EntradaKwargAusente(caminho=caminho, conteudo=conteudo, regra=regra)
        for caminho, conteudo in arquivos_para_regra(root, descoberta)
    ]


def entradas_git_interpretado_para_regra(
    root: Path, regra: RegraComparacaoNumericaSpec, descoberta: dict[str, Any]
) -> list[EntradaGitInterpretado]:
    """Mesmo espírito de `entradas_ast_para_regra`, para a Skill "comando
    git único interpretado"."""
    return [
        EntradaGitInterpretado(caminho=caminho, conteudo=conteudo, regra=regra)
        for caminho, conteudo in arquivos_para_regra(root, descoberta)
    ]


def entradas_execucao_comando_para_regra(
    root: Path, regra: RegraExecucaoComandoSpec, descoberta: dict[str, Any]
) -> list[EntradaExecucaoComando]:
    """Mesmo espírito de `entradas_ast_para_regra`, para a Skill "executar
    comando externo, timeout, venv-aware"."""
    return [
        EntradaExecucaoComando(caminho=caminho, conteudo=conteudo, regra=regra)
        for caminho, conteudo in arquivos_para_regra(root, descoberta)
    ]


def entradas_dependencias_para_regra(
    root: Path, regra: RegraDependenciasSpec, descoberta: dict[str, Any]
) -> list[EntradaDependencias]:
    """Mesmo espírito de `entradas_ast_para_regra`, para a Skill "parsing
    TOML real de pyproject.toml"."""
    return [
        EntradaDependencias(caminho=caminho, conteudo=conteudo, regra=regra)
        for caminho, conteudo in arquivos_para_regra(root, descoberta)
    ]


def entradas_janela_para_regra(
    root: Path, regra: RegraJanelaSpec, descoberta: dict[str, Any]
) -> list[EntradaJanela]:
    """Mesmo espírito de `entradas_ast_para_regra` — reaproveita a
    descoberta `"arvore"`/`"glob"`/`"arquivo_fixo"` já existente (1 Missão
    por arquivo), só o handler ("janela de contexto por ocorrência") é
    novo."""
    return [
        EntradaJanela(caminho=caminho, conteudo=conteudo, regra=regra)
        for caminho, conteudo in arquivos_para_regra(root, descoberta)
    ]


def entradas_metrica_para_regra(
    root: Path, regra: RegraMetricaSpec, descoberta: dict[str, Any]
) -> list[EntradaMetrica]:
    """Mesmo espírito de `entradas_ast_para_regra` — reaproveita a
    descoberta `"arvore"`/`"glob"`/`"arquivo_fixo"` já existente (1 Missão
    por arquivo), só o handler ("métrica com limiar") é novo."""
    return [
        EntradaMetrica(caminho=caminho, conteudo=conteudo, regra=regra)
        for caminho, conteudo in arquivos_para_regra(root, descoberta)
    ]


def entradas_sec005_para_regra(
    root: Path, regra: RegraSec005Spec, descoberta: dict[str, Any]
) -> list[EntradaSec005]:
    """Mesmo espírito de `entradas_ast_para_regra`, para a Capability
    bespoke SEC-005."""
    return [
        EntradaSec005(caminho=caminho, conteudo=conteudo, regra=regra)
        for caminho, conteudo in arquivos_para_regra(root, descoberta)
    ]


def entradas_fe001_para_regra(
    root: Path, regra: RegraFe001Spec, descoberta: dict[str, Any]
) -> list[EntradaFe001]:
    """Mesmo espírito de `entradas_ast_para_regra`, para a Capability
    bespoke FE-001 — reaproveita a descoberta `"regex_agregado"` já
    existente (empacota TODOS os arquivos como JSON numa única Missão),
    só o handler (agregação com agrupamento por nome exportado) é novo."""
    return [
        EntradaFe001(caminho=caminho, conteudo=conteudo, regra=regra)
        for caminho, conteudo in arquivos_para_regra(root, descoberta)
    ]


def entradas_rev006_para_regra(
    root: Path, regra: RegraRev006Spec, descoberta: dict[str, Any]
) -> list[EntradaRev006]:
    """Mesmo espírito de `entradas_a11y003_para_regra`, para a Capability
    bespoke REV-006 — reaproveita a descoberta genérica `"arvore"`."""
    return [
        EntradaRev006(caminho=caminho, conteudo=conteudo, regra=regra)
        for caminho, conteudo in arquivos_para_regra(root, descoberta)
    ]


def entradas_sec008_para_regra(
    root: Path, regra: RegraSec008Spec, descoberta: dict[str, Any]
) -> list[EntradaSec008]:
    """Mesmo espírito de `entradas_a11y003_para_regra`, para a Capability
    bespoke SEC-008 — reaproveita a descoberta genérica `"arvore"`."""
    return [
        EntradaSec008(caminho=caminho, conteudo=conteudo, regra=regra)
        for caminho, conteudo in arquivos_para_regra(root, descoberta)
    ]


def entradas_sre006_para_regra(
    root: Path, regra: RegraSre006Spec, descoberta: dict[str, Any]
) -> list[EntradaSre006]:
    """Mesmo espírito de `entradas_a11y003_para_regra`, para a Capability
    bespoke SRE-006."""
    return [
        EntradaSre006(caminho=caminho, conteudo=conteudo, regra=regra)
        for caminho, conteudo in arquivos_para_regra(root, descoberta)
    ]


def entradas_sec009_para_regra(
    root: Path, regra: RegraSec009Spec, descoberta: dict[str, Any]
) -> list[EntradaSec009]:
    """Mesmo espírito de `entradas_a11y003_para_regra`, para a Capability
    bespoke SEC-009 — reaproveita a descoberta genérica `"arvore"`."""
    return [
        EntradaSec009(caminho=caminho, conteudo=conteudo, regra=regra)
        for caminho, conteudo in arquivos_para_regra(root, descoberta)
    ]


def entradas_pd001_para_regra(
    root: Path, regra: RegraPd001Spec, descoberta: dict[str, Any]
) -> list[EntradaPd001]:
    """Mesmo espírito de `entradas_a11y003_para_regra`, para a Capability
    bespoke PD-001 — reaproveita a descoberta genérica `"arvore"`."""
    return [
        EntradaPd001(caminho=caminho, conteudo=conteudo, regra=regra)
        for caminho, conteudo in arquivos_para_regra(root, descoberta)
    ]


def entradas_pd009_para_regra(
    root: Path, regra: RegraPd009Spec, descoberta: dict[str, Any]
) -> list[EntradaPd009]:
    """Mesmo espírito de `entradas_ast_para_regra`, para a Capability
    bespoke PD-009."""
    return [
        EntradaPd009(caminho=caminho, conteudo=conteudo, regra=regra)
        for caminho, conteudo in arquivos_para_regra(root, descoberta)
    ]


def entradas_pd010_para_regra(
    root: Path, regra: RegraPd010Spec, descoberta: dict[str, Any]
) -> list[EntradaPd010]:
    """Mesmo espírito de `entradas_ast_para_regra`, para a Capability
    bespoke PD-010."""
    return [
        EntradaPd010(caminho=caminho, conteudo=conteudo, regra=regra)
        for caminho, conteudo in arquivos_para_regra(root, descoberta)
    ]


def entradas_perf004_para_regra(
    root: Path, regra: RegraPerf004Spec, descoberta: dict[str, Any]
) -> list[EntradaPerf004]:
    """Mesmo espírito de `entradas_a11y003_para_regra`, para a Capability
    bespoke PERF-004 — reaproveita a descoberta genérica `"arvore"`."""
    return [
        EntradaPerf004(caminho=caminho, conteudo=conteudo, regra=regra)
        for caminho, conteudo in arquivos_para_regra(root, descoberta)
    ]


def entradas_pd011_para_regra(
    root: Path, regra: RegraPd011Spec, descoberta: dict[str, Any]
) -> list[EntradaPd011]:
    """Mesmo espírito de `entradas_ast_para_regra`, para a Capability
    bespoke PD-011."""
    return [
        EntradaPd011(caminho=caminho, conteudo=conteudo, regra=regra)
        for caminho, conteudo in arquivos_para_regra(root, descoberta)
    ]


def entradas_qaauto001_para_regra(
    root: Path, regra: RegraQaAuto001Spec, descoberta: dict[str, Any]
) -> list[EntradaQaAuto001]:
    """Mesmo espírito de `entradas_ast_para_regra`, para a Capability
    bespoke QA-AUTO-001."""
    return [
        EntradaQaAuto001(caminho=caminho, conteudo=conteudo, regra=regra)
        for caminho, conteudo in arquivos_para_regra(root, descoberta)
    ]


def entradas_fin005_para_regra(
    root: Path, regra: RegraFin005Spec, descoberta: dict[str, Any]
) -> list[EntradaFin005]:
    """Mesmo espírito de `entradas_a11y003_para_regra`, para a Capability
    bespoke FIN-005 — reaproveita a descoberta genérica `"arvore"`."""
    return [
        EntradaFin005(caminho=caminho, conteudo=conteudo, regra=regra)
        for caminho, conteudo in arquivos_para_regra(root, descoberta)
    ]


def entradas_doc004_para_regra(
    root: Path, regra: RegraDoc004Spec, descoberta: dict[str, Any]
) -> list[EntradaDoc004]:
    """Mesmo espírito de `entradas_ast_para_regra`, para a Capability
    bespoke DOC-004."""
    return [
        EntradaDoc004(caminho=caminho, conteudo=conteudo, regra=regra)
        for caminho, conteudo in arquivos_para_regra(root, descoberta)
    ]


def entradas_qaauto003_para_regra(
    root: Path, regra: RegraQaAuto003Spec, descoberta: dict[str, Any]
) -> list[EntradaQaAuto003]:
    """Mesmo espírito de `entradas_ast_para_regra`, para a Capability
    bespoke QA-AUTO-003."""
    return [
        EntradaQaAuto003(caminho=caminho, conteudo=conteudo, regra=regra)
        for caminho, conteudo in arquivos_para_regra(root, descoberta)
    ]


def entradas_feapi_para_regra(
    root: Path, regra: RegraFeApiSpec, descoberta: dict[str, Any]
) -> list[EntradaFeApi]:
    """Mesmo espírito de `entradas_ast_para_regra`, para a Capability
    bespoke FE-API."""
    return [
        EntradaFeApi(caminho=caminho, conteudo=conteudo, regra=regra)
        for caminho, conteudo in arquivos_para_regra(root, descoberta)
    ]


def entradas_arch003_para_regra(
    root: Path, regra: RegraArch003Spec, descoberta: dict[str, Any]
) -> list[EntradaArch003]:
    """Mesmo espírito de `entradas_ast_para_regra`, para a Capability
    bespoke ARCH-003."""
    return [
        EntradaArch003(caminho=caminho, conteudo=conteudo, regra=regra)
        for caminho, conteudo in arquivos_para_regra(root, descoberta)
    ]


def entradas_ba004_para_regra(
    root: Path, regra: RegraBa004Spec, descoberta: dict[str, Any]
) -> list[EntradaBa004]:
    """Mesmo espírito de `entradas_ast_para_regra`, para a Capability
    bespoke BA-004."""
    return [
        EntradaBa004(caminho=caminho, conteudo=conteudo, regra=regra)
        for caminho, conteudo in arquivos_para_regra(root, descoberta)
    ]


def entradas_ba005_para_regra(
    root: Path, regra: RegraBa005Spec, descoberta: dict[str, Any]
) -> list[EntradaBa005]:
    """Mesmo espírito de `entradas_ast_para_regra`, para a Capability
    bespoke BA-005."""
    return [
        EntradaBa005(caminho=caminho, conteudo=conteudo, regra=regra)
        for caminho, conteudo in arquivos_para_regra(root, descoberta)
    ]


def entradas_be010_para_regra(
    root: Path, regra: RegraBe010Spec, descoberta: dict[str, Any]
) -> list[EntradaBe010]:
    """Mesmo espírito de `entradas_ast_para_regra`, para a Capability
    bespoke BE-010."""
    return [
        EntradaBe010(caminho=caminho, conteudo=conteudo, regra=regra)
        for caminho, conteudo in arquivos_para_regra(root, descoberta)
    ]


def entradas_be013_para_regra(
    root: Path, regra: RegraBe013Spec, descoberta: dict[str, Any]
) -> list[EntradaBe013]:
    """Mesmo espírito de `entradas_ast_para_regra`, para a Capability
    bespoke BE-013."""
    return [
        EntradaBe013(caminho=caminho, conteudo=conteudo, regra=regra)
        for caminho, conteudo in arquivos_para_regra(root, descoberta)
    ]


def entradas_sec007_para_regra(
    root: Path, regra: RegraSec007Spec, descoberta: dict[str, Any]
) -> list[EntradaSec007]:
    """Mesmo espírito de `entradas_ast_para_regra`, para a Capability
    bespoke SEC-007."""
    return [
        EntradaSec007(caminho=caminho, conteudo=conteudo, regra=regra)
        for caminho, conteudo in arquivos_para_regra(root, descoberta)
    ]


def entradas_sup001_para_regra(
    root: Path, regra: RegraSup001Spec, descoberta: dict[str, Any]
) -> list[EntradaSup001]:
    """Mesmo espírito de `entradas_ast_para_regra`, para a Capability
    bespoke SUP-001."""
    return [
        EntradaSup001(caminho=caminho, conteudo=conteudo, regra=regra)
        for caminho, conteudo in arquivos_para_regra(root, descoberta)
    ]


def entradas_ora005_para_regra(
    root: Path, regra: RegraOra005Spec, descoberta: dict[str, Any]
) -> list[EntradaOra005]:
    """Mesmo espírito de `entradas_ast_para_regra`, para a Capability
    bespoke ORA-005 — reaproveita a descoberta `"arvore"` já existente (1
    Missão por arquivo), só o handler é bespoke."""
    return [
        EntradaOra005(caminho=caminho, conteudo=conteudo, regra=regra)
        for caminho, conteudo in arquivos_para_regra(root, descoberta)
    ]


def entradas_ora004_para_regra(
    root: Path, regra: RegraOra004Spec, descoberta: dict[str, Any]
) -> list[EntradaOra004]:
    """Mesmo espírito de `entradas_ast_para_regra`, para a Capability
    bespoke ORA-004."""
    return [
        EntradaOra004(caminho=caminho, conteudo=conteudo, regra=regra)
        for caminho, conteudo in arquivos_para_regra(root, descoberta)
    ]


def entradas_agregadas_para_regra(
    root: Path, regra: RegraAgregadaSpec, descoberta: dict[str, Any]
) -> list[EntradaAgregada]:
    """Mesmo espírito de `entradas_ast_para_regra`, para a Skill "regex
    agregado sobre múltiplos arquivos"."""
    return [
        EntradaAgregada(caminho=caminho, conteudo=conteudo, regra=regra)
        for caminho, conteudo in arquivos_para_regra(root, descoberta)
    ]


def entradas_de003_para_regra(
    root: Path, regra: RegraDe003Spec, descoberta: dict[str, Any]
) -> list[EntradaDe003]:
    """Mesmo espírito de `entradas_ast_para_regra`, para a Capability
    bespoke DE-003."""
    return [
        EntradaDe003(caminho=caminho, conteudo=conteudo, regra=regra)
        for caminho, conteudo in arquivos_para_regra(root, descoberta)
    ]


def arquivos_para_regra(root: Path, descoberta: dict[str, Any]) -> list[tuple[str, str | None]]:
    """Retorna `(caminho_relativo, conteudo_ou_None)` para cada arquivo
    relevante segundo `descoberta["tipo"]`."""
    tipo = descoberta["tipo"]
    if tipo == "arquivo_fixo":
        caminho = descoberta["caminho"]
        conteudo = _ler_ou_marcar_presente(root, caminho)
        # `caminho_relatorio` (opcional) sobrescreve o caminho reportado no
        # achado/fingerprint sem afetar qual caminho e checado no disco -
        # replica DE-002 do motor legado, que checa "alembic"/"migrations"/
        # "alembic.ini" mas reporta o achado com path="." (raiz do repo).
        caminho_relatorio = descoberta.get("caminho_relatorio", caminho)
        return [(caminho_relatorio, conteudo)]
    if tipo == "arvore":
        return _arquivos_em_arvore(root, descoberta)
    if tipo == "glob":
        return _arquivos_via_glob(root, descoberta)
    if tipo == "git":
        return _resultado_de_comando_git(root, descoberta)
    if tipo == "subprocess":
        return _resultado_de_subprocess(root, descoberta)
    if tipo == "toml_dependencias":
        return _resultado_de_dependencias(root, descoberta)
    if tipo == "de003":
        return _resultado_de003(root, descoberta)
    if tipo == "ora004":
        return _resultado_ora004(root, descoberta)
    if tipo == "regex_agregado":
        return _resultado_regex_agregado(root, descoberta)
    if tipo == "arch003":
        return _resultado_arch003(root, descoberta)
    if tipo == "feapi":
        return _resultado_feapi(root, descoberta)
    if tipo == "be010":
        return _resultado_be010(root, descoberta)
    if tipo == "pd011":
        return _resultado_pd011(root, descoberta)
    if tipo == "qaauto001":
        return _resultado_qaauto001(root, descoberta)
    if tipo == "govdebt001":
        return _resultado_govdebt001(root, descoberta)
    if tipo == "qaauto003":
        return _resultado_qaauto003(root, descoberta)
    if tipo == "doc004":
        return _resultado_doc004(root, descoberta)
    if tipo == "pd009":
        return _resultado_pd009(root, descoberta)
    if tipo == "pd010":
        return _resultado_pd010(root, descoberta)
    if tipo == "sre006":
        return _resultado_sre006(root, descoberta)
    if tipo == "cs005":
        return _resultado_cs005(root, descoberta)
    raise TipoDescobertaDesconhecido(tipo)


def _resultado_pd011(root: Path, descoberta: dict[str, Any]) -> list[tuple[str, str | None]]:
    """1 única Missão: agrega o texto de `frontend_dirs` (.ts/.tsx) e de
    `src/` (recursivo, .py) SEPARADAMENTE — o handler precisa saber ONDE
    o padrão aparece, não só SE aparece, então os dois textos não podem
    ser misturados numa fonte só (diferente de `regex_agregado`)."""
    caminho_relatorio = descoberta.get("caminho_relatorio", "frontend/src/")
    frontend_dirs = descoberta.get("frontend_dirs", ["frontend/src"])
    backend_dir = descoberta.get("backend_dir", "src")

    frontend_arvore = {"scope_dirs": frontend_dirs, "extensoes": [".ts", ".tsx"]}
    frontend_text = " ".join(
        conteudo or "" for _, conteudo in _arquivos_em_arvore(root, frontend_arvore)
    )

    backend_arvore = {"scope_dirs": [backend_dir], "extensoes": [".py"]}
    backend_text = " ".join(
        conteudo or "" for _, conteudo in _arquivos_em_arvore(root, backend_arvore)
    )

    payload = {"frontend_text": frontend_text, "backend_text": backend_text}
    return [(caminho_relatorio, json.dumps(payload))]


def _resultado_feapi(root: Path, descoberta: dict[str, Any]) -> list[tuple[str, str | None]]:
    """1 Missão por arquivo de rotas (`api/**/*.py`), cada uma carregando o
    PRÓPRIO conteúdo (para extração de rotas via AST no handler) + o texto
    agregado do frontend (`frontend/src/api/**/*.ts(x)`, lido uma única
    vez) — empacotados como JSON. Replica `collect_fastapi_routes` +
    `ctx.ts_files(ctx.frontend_api_dir)` do legado."""
    scope_dirs_api = descoberta.get("scope_dirs", ["api"])
    caminho_frontend_api = descoberta.get("caminho_frontend_api", "frontend/src/api")

    frontend_arvore = {"scope_dirs": [caminho_frontend_api], "extensoes": [".ts", ".tsx"]}
    frontend_text = " ".join(
        conteudo or "" for _, conteudo in _arquivos_em_arvore(root, frontend_arvore)
    )

    api_arvore = {"scope_dirs": scope_dirs_api, "extensoes": [".py"]}
    resultado: list[tuple[str, str | None]] = []
    for rel, conteudo in _arquivos_em_arvore(root, api_arvore):
        payload = {"api_src": conteudo or "", "frontend_text": frontend_text}
        resultado.append((rel, json.dumps(payload)))
    return resultado


def _local_module_names(root: Path) -> list[str]:
    """Replica `RepoContext.local_module_names()`: nomes de topo (diretórios
    e stems de `.py`) direto sob a raiz do repo, mais os nomes hardcoded
    que o legado sempre inclui."""
    nomes: set[str] = set()
    try:
        for p in root.iterdir():
            if p.name.startswith("."):
                continue
            if p.is_dir():
                nomes.add(p.name)
            elif p.suffix == ".py":
                nomes.add(p.stem)
    except OSError:
        pass
    nomes.update({"src", "app", "core", "tests", "test"})
    return sorted(nomes)


def _resultado_cs005(root: Path, descoberta: dict[str, Any]) -> list[tuple[str, str | None]]:
    """1 Missão por arquivo candidato (`api_dir/**/*.py`), cada uma
    carregando o PRÓPRIO conteúdo + o texto agregado do "gate global"
    (`api/middleware/*.py` + `main.py`/`app.py` na raiz e em `api_dir`,
    lido uma única vez) como JSON — replica o `return` antecipado do
    legado quando qualquer candidato do gate já resolve correlation/
    request/trace id globalmente."""
    api_dir = descoberta.get("api_dir", "api")
    middleware_dir_rel = descoberta.get("middleware_dir", "api/middleware")

    textos_gate: list[str] = []
    middleware_dir = root / middleware_dir_rel
    if middleware_dir.exists():
        for mf in sorted(middleware_dir.glob("*.py")):
            textos_gate.append(_ler_texto(mf))
    for nome in ("main.py", "app.py"):
        for base_rel in ("", api_dir):
            caminho_rel = f"{base_rel}/{nome}" if base_rel else nome
            texto = _ler_ou_marcar_presente(root, caminho_rel)
            if texto is not None:
                textos_gate.append(texto)

    middleware_global_texto = " ".join(textos_gate)

    api_arvore = {"scope_dirs": [api_dir], "extensoes": [".py"]}
    resultado: list[tuple[str, str | None]] = []
    for rel, conteudo in _arquivos_em_arvore(root, api_arvore):
        payload = {"api_src": conteudo or "", "middleware_global_texto": middleware_global_texto}
        resultado.append((rel, json.dumps(payload)))
    return resultado


def _resultado_sre006(root: Path, descoberta: dict[str, Any]) -> list[tuple[str, str | None]]:
    """1 única Missão: se `gunicorn.conf.py` existe, empacota SÓ ele
    (prioridade — replica o `return` incondicional do legado após checar
    esse arquivo). Senão, empacota `scripts/*.sh` + `scripts/*.py` (nessa
    ordem, cada grupo ordenado) como JSON."""
    gunicorn_conf_path = descoberta.get("gunicorn_conf_path", "gunicorn.conf.py")
    scripts_dir_rel = descoberta.get("scripts_dir", "scripts")
    caminho_relatorio = descoberta.get("caminho_relatorio", gunicorn_conf_path)

    texto_gunicorn = _ler_ou_marcar_presente(root, gunicorn_conf_path)
    if texto_gunicorn is not None:
        payload = {"gunicorn_conf_texto": texto_gunicorn}
        return [(caminho_relatorio, json.dumps(payload))]

    scripts_dir = root / scripts_dir_rel
    if not scripts_dir.exists():
        return [(caminho_relatorio, None)]

    scripts: list[list[str]] = []
    for caminho in sorted(scripts_dir.glob("*.sh")) + sorted(scripts_dir.glob("*.py")):
        scripts.append([_rel_posix(root, caminho), _ler_texto(caminho)])

    payload_scripts: dict[str, Any] = {"scripts": scripts}
    return [(caminho_relatorio, json.dumps(payload_scripts))]


def _resultado_pd010(root: Path, descoberta: dict[str, Any]) -> list[tuple[str, str | None]]:
    """Combina 1 Missão para o arquivo backend fixo (`api/routers/
    sim.py`, se existir) + 1 Missão por arquivo frontend cujo stem
    contém "sim" (case-insensitive) ou "SimuladorFree" (case-sensitive,
    replica o `and` do legado: `"SimuladorFree" not in p.stem and "sim"
    not in p.stem.lower()`)."""
    sim_router_path = descoberta.get("sim_router_path", "api/routers/sim.py")
    frontend_dirs: list[str] = descoberta.get("frontend_dirs", ["frontend/src"])

    resultado: list[tuple[str, str | None]] = []
    texto_backend = _ler_ou_marcar_presente(root, sim_router_path)
    if texto_backend is not None:
        resultado.append((sim_router_path, texto_backend))

    frontend_arvore = {"scope_dirs": frontend_dirs, "extensoes": [".ts", ".tsx"]}
    for rel, conteudo in _arquivos_em_arvore(root, frontend_arvore):
        stem = rel.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        if "SimuladorFree" not in stem and "sim" not in stem.lower():
            continue
        resultado.append((rel, conteudo))

    return resultado


def _resultado_pd009(root: Path, descoberta: dict[str, Any]) -> list[tuple[str, str | None]]:
    """1 única Missão: empacota o conteúdo de `App.tsx` (fonte das
    ocorrências de rota) + os textos de uma LISTA FIXA de arquivos de nav
    como JSON. Se `App.tsx` não existir, `conteudo=None` (replica o
    `return` antecipado do legado)."""
    app_path = descoberta.get("app_path", "frontend/src/App.tsx")
    nav_paths: list[str] = descoberta.get(
        "nav_paths",
        ["frontend/src/components/Layout.tsx", "frontend/src/components/NotifBell.tsx"],
    )
    caminho_relatorio = descoberta.get("caminho_relatorio", app_path)

    app_texto = _ler_ou_marcar_presente(root, app_path)
    if app_texto is None:
        return [(caminho_relatorio, None)]

    nav_textos = [t for p in nav_paths if (t := _ler_ou_marcar_presente(root, p)) is not None]
    payload = {"app_texto": app_texto, "nav_textos": nav_textos}
    return [(caminho_relatorio, json.dumps(payload))]


def _resultado_doc004(root: Path, descoberta: dict[str, Any]) -> list[tuple[str, str | None]]:
    """1 única Missão: empacota `pyproject.toml` + `CHANGELOG.md` como
    JSON. Se qualquer um dos dois não existir, `conteudo=None` (replica
    o `return` antecipado do legado)."""
    pyproject_path = descoberta.get("pyproject_path", "pyproject.toml")
    changelog_path = descoberta.get("changelog_path", "CHANGELOG.md")
    caminho_relatorio = descoberta.get("caminho_relatorio", changelog_path)

    pyproject_texto = _ler_ou_marcar_presente(root, pyproject_path)
    changelog_texto = _ler_ou_marcar_presente(root, changelog_path)
    if pyproject_texto is None or changelog_texto is None:
        return [(caminho_relatorio, None)]

    payload = {"pyproject_texto": pyproject_texto, "changelog_texto": changelog_texto}
    return [(caminho_relatorio, json.dumps(payload))]


def _resultado_qaauto003(root: Path, descoberta: dict[str, Any]) -> list[tuple[str, str | None]]:
    """1 única Missão: checa a existência de cada path em `required_paths`
    e empacota os AUSENTES (na mesma ordem da lista) como JSON."""
    required_paths: list[str] = descoberta.get("required_paths", [])
    caminho_relatorio = descoberta.get("caminho_relatorio", "e2e/smoke")

    missing = [p for p in required_paths if not (root / p).exists()]
    payload = {"missing": missing, "total": len(required_paths)}
    return [(caminho_relatorio, json.dumps(payload))]


def _resultado_govdebt001(root: Path, descoberta: dict[str, Any]) -> list[tuple[str, str | None]]:
    """1 única Missão: empacota `Batman/ledger.json` (parseado) + a lista
    de códigos com deferimento explícito (`Batman/config/deferred.json`,
    chaves de `deferred`) como JSON. Se `ledger.json` não existe ou é
    ilegível, a Missão carrega `conteudo=None` (replica o `return`
    antecipado do legado)."""
    ledger_path = descoberta.get("ledger_path", "Batman/ledger.json")
    deferred_path = descoberta.get("deferred_path", "Batman/config/deferred.json")
    caminho_relatorio = descoberta.get("caminho_relatorio", ledger_path)

    texto_ledger = _ler_ou_marcar_presente(root, ledger_path)
    if not texto_ledger:
        return [(caminho_relatorio, None)]

    try:
        ledger = json.loads(texto_ledger)
    except json.JSONDecodeError:
        return [(caminho_relatorio, None)]

    deferred_codes: list[str] = []
    texto_deferred = _ler_ou_marcar_presente(root, deferred_path)
    if texto_deferred:
        try:
            deferred = json.loads(texto_deferred)
            deferred_codes = sorted(deferred.get("deferred", {}).keys())
        except json.JSONDecodeError:
            pass

    payload = {"ledger": ledger, "deferred_codes": deferred_codes}
    return [(caminho_relatorio, json.dumps(payload))]


def _resultado_be010(root: Path, descoberta: dict[str, Any]) -> list[tuple[str, str | None]]:
    """1 única Missão: empacota `pyproject.toml` + nomes de módulo local
    (listagem de diretório, não conteúdo de arquivo) + TODOS os `.py` de
    `scope_dirs` (na ORDEM dada, preservando a ordem de inserção do dict
    — replica `seen.setdefault` do legado, que reporta o PRIMEIRO arquivo
    onde um import de terceiro aparece) como JSON."""
    caminho_pyproject = descoberta.get("caminho_pyproject", "pyproject.toml")
    caminho_relatorio = descoberta.get("caminho_relatorio", caminho_pyproject)
    scope_dirs = descoberta.get("scope_dirs", ["api", "src", "dashboard", "pages"])

    pyproject_texto = _ler_ou_marcar_presente(root, caminho_pyproject)
    if pyproject_texto is None:
        return [(caminho_relatorio, None)]

    arquivos: dict[str, str] = {}
    for escopo in scope_dirs:
        arvore = {"scope_dirs": [escopo], "extensoes": [".py"]}
        for rel, conteudo in _arquivos_em_arvore(root, arvore):
            if conteudo is not None:
                arquivos[rel] = conteudo

    payload = {
        "pyproject_texto": pyproject_texto,
        "local_modules": _local_module_names(root),
        "arquivos": arquivos,
    }
    return [(caminho_relatorio, json.dumps(payload))]


def _resultado_qaauto001(root: Path, descoberta: dict[str, Any]) -> list[tuple[str, str | None]]:
    """1 Missão por router candidato (`api/routers/*.py`), cada uma
    carregando a MESMA lista agregada de stems de teste (`tests/**/
    test_*.py`, prefixo `test_` removido — replica `p.stem.replace(
    "test_", "")` do legado) como JSON. Se `tests/` não existe, nenhuma
    Missão é gerada (replica o `return` antecipado do legado)."""
    tests_dir = descoberta.get("tests_dir", "tests")
    routers_dir = descoberta.get("routers_dir", "api/routers")

    if not (root / tests_dir).is_dir():
        return []

    test_stems = sorted(
        {
            rel.replace("\\", "/").rsplit("/", 1)[-1].rsplit(".", 1)[0].replace("test_", "")
            for rel, _ in _arquivos_em_arvore(
                root, {"scope_dirs": [tests_dir], "extensoes": [".py"]}
            )
            if rel.replace("\\", "/").rsplit("/", 1)[-1].startswith("test_")
        }
    )
    payload = json.dumps({"test_stems": test_stems})

    routers_arvore = {"scope_dirs": [routers_dir], "extensoes": [".py"]}
    return [(rel, payload) for rel, _ in _arquivos_em_arvore(root, routers_arvore)]


def _resultado_arch003(root: Path, descoberta: dict[str, Any]) -> list[tuple[str, str | None]]:
    """1 Missão por página candidata (`pages/*.py`), cada uma carregando o
    MESMO conteúdo do agregador (`dashboard/app.py`) como `conteudo` — o
    handler bespoke ARCH-003 só verifica se o próprio nome (stem) da
    página aparece nesse texto compartilhado. Replica `RepoContext.
    dashboard_app`/`pages_dir` do legado."""
    caminho_agregador = descoberta.get("caminho_agregador", "dashboard/app.py")
    scope_dirs = descoberta.get("scope_dirs", ["pages"])
    conteudo_agregador = _ler_ou_marcar_presente(root, caminho_agregador)

    descoberta_arvore = {
        "scope_dirs": scope_dirs,
        "extensoes": descoberta.get("extensoes", [".py"]),
    }
    paginas = _arquivos_em_arvore(root, descoberta_arvore)
    return [(rel, conteudo_agregador) for rel, _ in paginas]


def _resultado_de003(root: Path, descoberta: dict[str, Any]) -> list[tuple[str, str | None]]:
    tables_path = descoberta.get("tables_path", "api/database/tables.py")
    init_db_path = descoberta.get("init_db_path", "api/database/init_db.py")
    lookback = descoberta.get("lookback", 15)
    caminho_relatorio = descoberta.get("caminho_relatorio", tables_path)

    if not (root / tables_path).exists() or not (root / init_db_path).exists():
        payload: dict[str, Any] = {"aplica": False}
        return [(caminho_relatorio, json.dumps(payload))]

    args = (
        "log",
        f"-{lookback}",
        "--pretty=format:COMMIT:%H",
        "-p",
        "--unified=30",
        "--",
        tables_path,
    )
    try:
        resultado = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, timeout=30
        )
        log = resultado.stdout.strip()
    except Exception:
        log = ""

    payload = {
        "aplica": True,
        "init_db_src": _ler_texto(root / init_db_path),
        "tables_src": _ler_texto(root / tables_path),
        "git_log": log,
    }
    return [(caminho_relatorio, json.dumps(payload))]


def _resultado_ora004(root: Path, descoberta: dict[str, Any]) -> list[tuple[str, str | None]]:
    caminho_relatorio = descoberta.get("caminho_relatorio", ".")
    enums_path = descoberta.get("enums_path")

    descoberta_arvore = {
        "scope_dirs": descoberta.get("scope_dirs", []),
        "extensoes": [".py"],
        # replica oracle.py: `any(part.startswith(("test","conftest")) for
        # part in parts)` — qualquer segmento do caminho, não só o nome do
        # arquivo (arquivo em si coberto por excluir_nome_prefixo). Legado
        # não faz case-fold aqui, só o "tests"/"test_*" minúsculo real.
        "excluir_caminho_contem": ["/test", "/conftest"],
        "excluir_nome_prefixo": ["test", "conftest"],
    }
    arquivos = {
        rel: (conteudo or "") for rel, conteudo in _arquivos_em_arvore(root, descoberta_arvore)
    }

    enums_src = None
    if enums_path and (root / enums_path).exists():
        enums_src = _ler_texto(root / enums_path)

    payload: dict[str, Any] = {"arquivos": arquivos, "enums_src": enums_src}
    return [(caminho_relatorio, json.dumps(payload))]


def _resultado_regex_agregado(
    root: Path, descoberta: dict[str, Any]
) -> list[tuple[str, str | None]]:
    """Empacota o conteúdo de VÁRIOS arquivos (potencialmente de múltiplas
    fontes de tipos DIFERENTES — ex.: VPS-012 usa `glob` não-recursivo
    `scripts/*.sh` porque o legado usa `Path.glob` (só filhos diretos), não
    `Path.rglob`) como JSON para a Skill "regex agregado sobre múltiplos
    arquivos" (`regex_agregado_multi_arquivo.py`). `fontes` (opcional):
    lista de descobertas independentes, cada uma com seu próprio `tipo`
    (`arvore`/`glob`/`arquivo_fixo`, despachadas via `arquivos_para_regra`
    — mesmo dispatcher genérico usado no nível superior); sem `fontes`, a
    própria `descoberta` é usada como fonte única do tipo `arvore` (mesma
    convenção de `scope_dirs`/`extensoes` direto no nível superior)."""
    caminho_relatorio = descoberta.get("caminho_relatorio", ".")
    fontes = descoberta.get("fontes") or [{**descoberta, "tipo": "arvore"}]

    arquivos: dict[str, str] = {}
    for fonte in fontes:
        for rel, conteudo in arquivos_para_regra(root, fonte):
            if conteudo is not None:
                arquivos[rel] = conteudo

    payload: dict[str, Any] = {"arquivos": arquivos}
    return [(caminho_relatorio, json.dumps(payload))]


def _resultado_de_dependencias(
    root: Path, descoberta: dict[str, Any]
) -> list[tuple[str, str | None]]:
    caminho_relatorio = descoberta.get("caminho_relatorio", "pyproject.toml")
    pyproject = root / "pyproject.toml"
    requirements = root / "requirements.txt"

    payload: dict[str, Any] = {
        "pyproject_texto": _ler_texto(pyproject) if pyproject.exists() else None,
        "requirements_texto": _ler_texto(requirements) if requirements.exists() else None,
        "arquivos_tests": _arquivos_py_como_dict(root, root / "tests"),
        "arquivos_src": _arquivos_py_como_dict(root, root / "src"),
    }
    return [(caminho_relatorio, json.dumps(payload))]


def _arquivos_py_como_dict(root: Path, base: Path) -> dict[str, str]:
    if not base.exists():
        return {}
    return {
        str(caminho.relative_to(root)).replace("\\", "/"): _ler_texto(caminho)
        for caminho in sorted(base.rglob("*.py"))
    }


def _resultado_de_comando_git(
    root: Path, descoberta: dict[str, Any]
) -> list[tuple[str, str | None]]:
    """Replica `Batman/scan/base.py::RepoContext.git()` — nunca propaga
    falha/timeout como exceção, retorna string vazia (não `None`; `None`
    aqui significaria "arquivo ausente", semântica que não se aplica a saída
    de comando)."""
    args = descoberta["args"]
    caminho_relatorio = descoberta.get("caminho_relatorio", ".git")
    try:
        resultado = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=15,
        )
        conteudo = resultado.stdout.strip()
    except Exception:
        conteudo = ""
    return [(caminho_relatorio, conteudo)]


def _python_do_venv(root: Path) -> str:
    """Replica `_find_python()` duplicado em `oracle.py`/`robin.py` —
    prefere o Python do venv do projeto alvo; fallback para o Python que
    está rodando o Batman OS."""
    for candidato in (
        root / ".venv" / "Scripts" / "python.exe",
        root / ".venv" / "bin" / "python",
        root / "venv" / "Scripts" / "python.exe",
        root / "venv" / "bin" / "python",
    ):
        if candidato.exists():
            return str(candidato)
    return sys.executable


def _rodar_subprocess_cacheado(
    comando: tuple[str, ...], root: Path, timeout: int
) -> tuple[int, str, str]:
    """Cache por (comando, root) durante o processo — corrige a ausência de
    cache em `robin.py` (pytest rodava 1x por regra QA-RUN-*; aqui roda 1x
    para as 3) e replica o cache já existente em `oracle.py` (`_ruff_cache`,
    ORA-001/002/003). Nunca propaga timeout/ausência do comando como
    exceção — devolve um returncode sentinela (-2 timeout, -1 não
    encontrado), mesmo espírito de `RuffUnavailable`/`PytestUnavailable`."""
    chave = (str(root), *comando)
    if chave in _cache_subprocess:
        return _cache_subprocess[chave]
    try:
        resultado = subprocess.run(
            list(comando), cwd=root, capture_output=True, text=True, timeout=timeout
        )
        valor = (resultado.returncode, resultado.stdout, resultado.stderr)
    except subprocess.TimeoutExpired:
        valor = (-2, "", f"comando excedeu timeout de {timeout}s")
    except FileNotFoundError:
        valor = (-1, "", "comando não encontrado")
    _cache_subprocess[chave] = valor
    return valor


def _resultado_de_subprocess(
    root: Path, descoberta: dict[str, Any]
) -> list[tuple[str, str | None]]:
    caminho_relatorio = descoberta.get("caminho_relatorio", ".")
    requer_dir: str | None = descoberta.get("requer_dir")
    dir_requerido_existe = (root / requer_dir).exists() if requer_dir else None

    arquivos_teste_encontrados: list[str] = []
    padroes_teste = descoberta.get("glob_arquivos_teste")
    if padroes_teste and requer_dir and dir_requerido_existe:
        base = root / requer_dir
        for padrao in padroes_teste:
            arquivos_teste_encontrados.extend(
                str(p.relative_to(root)).replace("\\", "/") for p in base.rglob(padrao)
            )

    if requer_dir and dir_requerido_existe is False:
        payload_ausente: dict[str, Any] = {
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "dir_requerido_existe": False,
            "arquivos_teste_encontrados": [],
        }
        return [(caminho_relatorio, json.dumps(payload_ausente))]

    args = list(descoberta.get("args", []))
    dirs_condicionais = descoberta.get("dirs_condicionais")
    if dirs_condicionais is not None:
        existentes = [d for d in dirs_condicionais if (root / d).exists()]
        if not existentes:
            # replica oracle.py: nenhum dos dirs-alvo existe -> sucesso
            # vazio, nem roda o comando (`if not targets: rc=0, items=[]`).
            payload_vazio: dict[str, Any] = {"returncode": 0, "stdout": "[]", "stderr": ""}
            return [(caminho_relatorio, json.dumps(payload_vazio))]
        args = [*args, *existentes]

    python = _python_do_venv(root)
    comando = (python, "-m", descoberta["modulo"], *args)
    rc, stdout, stderr = _rodar_subprocess_cacheado(comando, root, descoberta.get("timeout", 60))

    payload: dict[str, Any] = {
        "returncode": rc,
        "stdout": stdout,
        "stderr": stderr,
        "dir_requerido_existe": dir_requerido_existe,
        "arquivos_teste_encontrados": arquivos_teste_encontrados,
    }
    return [(caminho_relatorio, json.dumps(payload))]


def _condicoes_adicionais_para(root: Path, descoberta: dict[str, Any]) -> list[CondicaoAdicional]:
    condicoes: list[CondicaoAdicional] = []
    for item in descoberta.get("condicoes_adicionais", []):
        tipo = item["tipo"]
        if tipo == "arquivo_fixo":
            conteudo = _ler_ou_marcar_presente(root, item["caminho"])
            if conteudo is None and item.get("vazio_se_ausente"):
                # arquivo ausente conta como "sem protecao", nao como
                # "nao ha nada para avaliar" (ver docstring de
                # capabilities/rules/regex_sobre_conteudo.py::
                # _condicao_simples_satisfeita, modo AUSENCIA).
                conteudo = ""
            condicoes.append(
                CondicaoAdicional(
                    caminho=item["caminho"],
                    conteudo=conteudo,
                    checar=ModoAvaliacao(item["checar"]),
                    pattern=item.get("pattern"),
                    ignore_case=item.get("ignore_case", False),
                )
            )
        elif tipo == "glob_existe":
            condicoes.append(_condicao_glob_existe(root, item))
        else:
            raise TipoDescobertaDesconhecido(tipo)
    return condicoes


def _condicao_glob_existe(root: Path, item: dict[str, Any]) -> CondicaoAdicional:
    padrao = item["padrao_recursivo"]
    excludes = item.get("excluir_caminho_contem", [])
    encontrado = any(
        not _excluido_por_substring(_rel_posix(root, caminho), excludes)
        for caminho in root.rglob(padrao)
        if caminho.is_file()
    )
    return CondicaoAdicional(
        caminho=padrao,
        conteudo="existe" if encontrado else None,
        checar=ModoAvaliacao(item["checar"]),
    )


def _arquivos_em_arvore(root: Path, descoberta: dict[str, Any]) -> list[tuple[str, str | None]]:
    resultado: list[tuple[str, str | None]] = []
    for escopo in descoberta.get("scope_dirs", []):
        base = root / escopo
        if not base.exists():
            continue
        candidatos: set[Path] = set()
        for extensao in descoberta.get("extensoes", []):
            candidatos.update(base.rglob(f"*{extensao}"))
        for caminho in sorted(candidatos):
            rel = _rel_posix(root, caminho)
            if _excluido(rel, caminho.name, descoberta):
                continue
            resultado.append((rel, _ler_texto(caminho)))
    return resultado


def _arquivos_via_glob(root: Path, descoberta: dict[str, Any]) -> list[tuple[str, str | None]]:
    resultado: list[tuple[str, str | None]] = []
    padroes = descoberta.get("padroes")
    if padroes:
        candidatos: set[Path] = set()
        for padrao in padroes:
            candidatos.update(root.glob(padrao))
        for caminho in sorted(candidatos):
            if caminho.is_file():
                resultado.append((_rel_posix(root, caminho), _ler_texto(caminho)))
        return resultado

    padrao_recursivo = descoberta.get("padrao_recursivo")
    if padrao_recursivo:
        excludes = descoberta.get("excluir_caminho_contem", [])
        for caminho in sorted(root.rglob(padrao_recursivo)):
            if not caminho.is_file():
                continue
            rel = _rel_posix(root, caminho)
            if _excluido_por_substring(rel, excludes):
                continue
            resultado.append((rel, _ler_texto(caminho)))
        return resultado

    raise TipoDescobertaDesconhecido("glob sem 'padroes' nem 'padrao_recursivo'")


def _excluido(rel_posix: str, nome_arquivo: str, descoberta: dict[str, Any]) -> bool:
    if _excluido_por_substring(
        rel_posix, descoberta.get("excluir_caminho_prefixo", []), prefixo=True
    ):
        return True
    if _excluido_por_substring(rel_posix, descoberta.get("excluir_caminho_contem", [])):
        return True
    if _excluido_por_substring(
        rel_posix.lower(), descoberta.get("excluir_caminho_contem_lower", [])
    ):
        return True
    if _excluido_por_substring(
        nome_arquivo, descoberta.get("excluir_nome_prefixo", []), prefixo=True
    ):
        return True
    return _excluido_por_substring(
        nome_arquivo.lower(), descoberta.get("excluir_nome_contem_lower", [])
    )


def _excluido_por_substring(valor: str, padroes: list[str], prefixo: bool = False) -> bool:
    if prefixo:
        return any(valor.startswith(p) for p in padroes)
    return any(p in valor for p in padroes)


def _ler_ou_marcar_presente(root: Path, caminho_rel: str) -> str | None:
    caminho = root / caminho_rel
    if not caminho.exists():
        return None
    if caminho.is_dir():
        return ""  # presenca confirmada; sem conteudo textual a avaliar
    return _ler_texto(caminho)


def _ler_texto(caminho: Path) -> str:
    try:
        return caminho.read_text(encoding="utf-8")
    except Exception:
        return ""


def _rel_posix(root: Path, caminho: Path) -> str:
    try:
        return caminho.relative_to(root).as_posix()
    except ValueError:
        return caminho.as_posix()
