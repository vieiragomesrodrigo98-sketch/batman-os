"""Compara os achados de todos os lotes migrados com o motor Batman legado
(`radar-preditivo/Batman/scan/engine.py::run`), rodando os dois contra o
MESMO repositório alvo real.

Divergência de fingerprint = bug de migração (não do alvo) — mesma
disciplina de shadow mode do Volume VI (Cap.24) antes de considerar o
legado substituível para os códigos já migrados: os dois motores rodam em
paralelo, sem que o legado pare de ser a fonte de verdade em produção.

Uso:
    python scripts/compare_migracao.py --radar-preditivo <caminho> [--legacy-python <python.exe>]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from batman_os.capabilities import registry_sdk  # noqa: E402
from batman_os.cli.descoberta_arquivos import registrar_capabilities_conhecidas  # noqa: E402
from batman_os.cli.scan_command import executar_scan  # noqa: E402

# Fase 1 do roadmap de plataforma (`.claude/plans/peaceful-wondering-hearth.md`):
# especificacoes de TODAS as Capabilities vem do registry_sdk, populado por
# `registrar_capabilities_conhecidas()` -- substitui a lista manual de ~48
# imports + concatenacoes que existia aqui antes (uma Capability nova nao
# precisa mais tocar este arquivo).
if not registry_sdk.registry():
    registrar_capabilities_conhecidas()
_TODOS_OS_ITENS: list[Any] = []
for _plugin in registry_sdk.registry().values():
    _TODOS_OS_ITENS.extend(_plugin.carregar_especificacoes())
_CODIGOS_MIGRADOS = sorted(item["regra"].codigo for item in _TODOS_OS_ITENS)

_SCRIPT_LEGADO = """
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(sys.argv[1])))

from Batman.scan import engine
from Batman.scan.base import RepoContext

ctx = RepoContext(root=Path(sys.argv[1]))
codigos = set(json.loads(sys.argv[2]))
findings = engine.run(ctx)

por_codigo = {}
for f in findings:
    if f.codigo in codigos:
        por_codigo.setdefault(f.codigo, []).append(f.fingerprint)

print(json.dumps(por_codigo))
"""


def _fingerprints_legado(radar_preditivo: Path, python_legado: Path) -> dict[str, list[str]]:
    resultado = subprocess.run(
        [
            str(python_legado),
            "-c",
            _SCRIPT_LEGADO,
            str(radar_preditivo),
            json.dumps(_CODIGOS_MIGRADOS),
        ],
        capture_output=True,
        text=True,
        check=True,
        cwd=radar_preditivo,
    )
    linha_json = resultado.stdout.strip().splitlines()[-1]
    return dict(json.loads(linha_json))


def _fingerprints_novos(radar_preditivo: Path) -> dict[str, list[str]]:
    resultado = executar_scan(radar_preditivo)
    por_codigo: dict[str, list[str]] = {}
    for achado in resultado.achados:
        por_codigo.setdefault(achado.codigo, []).append(achado.fingerprint)
    return por_codigo


def comparar(radar_preditivo: Path, python_legado: Path) -> int:
    legado = _fingerprints_legado(radar_preditivo, python_legado)
    novo = _fingerprints_novos(radar_preditivo)

    divergencias = 0
    for codigo in _CODIGOS_MIGRADOS:
        fp_legado = set(legado.get(codigo, []))
        fp_novo = set(novo.get(codigo, []))
        if fp_legado == fp_novo:
            print(f"[OK]         {codigo}: {len(fp_novo)} achado(s), fingerprints identicos")
        else:
            divergencias += 1
            so_legado = len(fp_legado - fp_novo)
            so_novo = len(fp_novo - fp_legado)
            print(
                f"[DIVERGENTE] {codigo}: legado={len(fp_legado)} novo={len(fp_novo)} "
                f"so_legado={so_legado} so_novo={so_novo}"
            )

    print(f"\n{len(_CODIGOS_MIGRADOS) - divergencias}/{len(_CODIGOS_MIGRADOS)} codigos convergem")
    return 1 if divergencias else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--radar-preditivo", required=True, type=Path)
    parser.add_argument("--legacy-python", type=Path, default=None)
    args = parser.parse_args(argv)

    radar_preditivo = args.radar_preditivo.resolve()
    python_legado = args.legacy_python or (radar_preditivo / ".venv" / "Scripts" / "python.exe")
    if not python_legado.exists():
        python_legado = Path(sys.executable)

    return comparar(radar_preditivo, python_legado)


if __name__ == "__main__":
    sys.exit(main())
