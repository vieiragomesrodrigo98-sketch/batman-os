#!/bin/sh
# Prova que o HEAD e auto-contido: materializa o HEAD num worktree efemero e
# monta o registry inteiro de la, comparando (tipos, specs) com a arvore de
# trabalho.
#
# Por que existe: pytest/mypy/ruff e o proprio pre-push rodam sempre na ARVORE
# DE TRABALHO, onde os arquivos existem. Nenhum verificador testava o que foi
# de fato commitado. O defeito apareceu duas vezes:
#   - 3d1f433: llm/anthropic_gateway.py commitado importando modulos nunca
#     commitados (ModuleNotFoundError num clone limpo);
#   - BATMANOS_UNTRACKED_47_01: cli/descoberta_arquivos.py importando
#     comp008/fin006/ora006, e a spec COMP-007.json faltando.
#
# A spec faltante e o caso mais perigoso: os loaders usam `glob("*.json")`, entao
# um spec ausente NAO levanta erro — a regra silenciosamente deixa de existir e o
# scan sai verde sem ter olhado nada. Por isso a medida conta specs, e nao apenas
# importa os modulos.
#
# O oraculo e auto-calibrado (HEAD comparado contra a arvore), nunca um numero
# fixo que apodrece a cada regra nova.
set -e

if [ "${BATMAN_SKIP_HEADCHECK:-0}" = "1" ]; then
    echo "[head-check] PULADO por BATMAN_SKIP_HEADCHECK=1"
    exit 0
fi

REPO="$(git rev-parse --show-toplevel)"
PY="$REPO/.venv/Scripts/python.exe"
[ -x "$PY" ] || PY="$REPO/.venv/bin/python"

WT="$REPO/../.batman-os-headcheck-$$"

to_win() {
    if command -v cygpath >/dev/null 2>&1; then
        cygpath -m "$1"
    else
        printf '%s' "$1"
    fi
}

limpar() {
    git -C "$REPO" worktree remove --force "$WT" >/dev/null 2>&1 || true
}
trap limpar EXIT

git -C "$REPO" worktree add --detach --quiet "$WT" HEAD
WTW="$(to_win "$WT")"
REPOW="$(to_win "$REPO")"

# Imprime "<qtd de tipos de regra> <qtd total de specs carregadas>".
# O assert de procedencia impede que um editable install em modo strict faca a
# medida do worktree importar, na verdade, o codigo da arvore de trabalho — o
# que devolveria verde mentindo.
MEDIR='
import pathlib, sys
import batman_os
raiz = pathlib.Path(batman_os.__file__).resolve().parents[1]
alvo = pathlib.Path(sys.argv[1]).resolve() / "src"
if raiz != alvo:
    sys.exit(f"ERRO: importou de {raiz}, nao de {alvo} — medida invalida")
from batman_os.capabilities.registry_sdk import registry, limpar_registry
from batman_os.cli.descoberta_arquivos import registrar_capabilities_conhecidas
limpar_registry()
registrar_capabilities_conhecidas()
r = registry()
print(f"{len(r)} {sum(len(p.carregar_especificacoes()) for p in r.values())}")
'

if ! HEAD_M="$(PYTHONPATH="$WTW/src" PYTHONDONTWRITEBYTECODE=1 "$PY" -B -c "$MEDIR" "$WTW" 2>&1)"; then
    echo "[head-check] FALHOU — o HEAD nem sequer importa."
    echo "$HEAD_M" | sed 's/^/    /'
    echo "  untracked em src/ e tests/ (candidatos a commit esquecido):"
    git -C "$REPO" ls-files --others --exclude-standard -- src tests | sed 's/^/    /'
    exit 1
fi

ARV_M="$(PYTHONPATH="$REPOW/src" PYTHONDONTWRITEBYTECODE=1 "$PY" -B -c "$MEDIR" "$REPOW")"

if [ "$HEAD_M" != "$ARV_M" ]; then
    echo "[head-check] FALHOU — o HEAD nao reproduz a arvore de trabalho."
    echo "  HEAD   : tipos/specs = $HEAD_M"
    echo "  arvore : tipos/specs = $ARV_M"
    echo "  untracked em src/ e tests/:"
    git -C "$REPO" ls-files --others --exclude-standard -- src tests | sed 's/^/    /'
    echo "  no index mas fora do HEAD (o modo de falha do 'git add X; git commit --only Y'):"
    git -C "$REPO" diff --name-only --cached HEAD -- src tests | sed 's/^/    /'
    exit 1
fi

echo "[head-check] OK — HEAD auto-contido (tipos/specs = $HEAD_M)."
