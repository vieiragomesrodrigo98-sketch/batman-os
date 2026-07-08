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

from batman_os.capabilities.rules.ast_kwarg_ausente import (
    EntradaKwargAusente,
    RegraKwargAusenteSpec,
)
from batman_os.capabilities.rules.ast_padrao_ausente import EntradaAst, RegraAstSpec
from batman_os.capabilities.rules.be013_http200_em_except import EntradaBe013, RegraBe013Spec
from batman_os.capabilities.rules.de003_coluna_sem_migration import EntradaDe003, RegraDe003Spec
from batman_os.capabilities.rules.execucao_comando_interpretada import (
    EntradaExecucaoComando,
    RegraExecucaoComandoSpec,
)
from batman_os.capabilities.rules.git_comando_interpretado import (
    EntradaGitInterpretado,
    RegraComparacaoNumericaSpec,
)
from batman_os.capabilities.rules.janela_contexto_regex import EntradaJanela, RegraJanelaSpec
from batman_os.capabilities.rules.metrica_com_limiar import EntradaMetrica, RegraMetricaSpec
from batman_os.capabilities.rules.ora004_status_typo import EntradaOra004, RegraOra004Spec
from batman_os.capabilities.rules.ora005_fallback_silencioso import EntradaOra005, RegraOra005Spec
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
from batman_os.capabilities.rules.sec005_fstring_sql import EntradaSec005, RegraSec005Spec
from batman_os.capabilities.rules.sec007_ddl_no_import import EntradaSec007, RegraSec007Spec
from batman_os.capabilities.rules.sup001_excecao_silenciada import (
    EntradaSup001,
    RegraSup001Spec,
)
from batman_os.capabilities.rules.toml_dependencias import (
    EntradaDependencias,
    RegraDependenciasSpec,
)

_cache_subprocess: dict[tuple[str, ...], tuple[int, str, str]] = {}


class TipoDescobertaDesconhecido(Exception):
    """Levantada quando `descoberta["tipo"]` (ou o `tipo` de uma condição
    adicional) não é um dos reconhecidos por este módulo."""


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
    raise TipoDescobertaDesconhecido(tipo)


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
