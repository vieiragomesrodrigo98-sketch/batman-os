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

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from batman_os.capabilities.rules.a11y002_loader import (  # noqa: E402
    carregar_especificacoes_a11y002,
)
from batman_os.capabilities.rules.a11y003_loader import (  # noqa: E402
    carregar_especificacoes_a11y003,
)
from batman_os.capabilities.rules.arch003_loader import (
    carregar_especificacoes_arch003,  # noqa: E402
)
from batman_os.capabilities.rules.ast_kwarg_ausente_loader import (  # noqa: E402
    carregar_especificacoes_kwarg_ausente,
)
from batman_os.capabilities.rules.ast_padrao_ausente_loader import (  # noqa: E402
    carregar_especificacoes_ast,
)
from batman_os.capabilities.rules.ba004_loader import carregar_especificacoes_ba004  # noqa: E402
from batman_os.capabilities.rules.ba005_loader import carregar_especificacoes_ba005  # noqa: E402
from batman_os.capabilities.rules.be010_loader import carregar_especificacoes_be010  # noqa: E402
from batman_os.capabilities.rules.be013_loader import carregar_especificacoes_be013  # noqa: E402
from batman_os.capabilities.rules.cs003_loader import carregar_especificacoes_cs003  # noqa: E402
from batman_os.capabilities.rules.cs005_loader import carregar_especificacoes_cs005  # noqa: E402
from batman_os.capabilities.rules.cto002_loader import carregar_especificacoes_cto002  # noqa: E402
from batman_os.capabilities.rules.cto004_loader import carregar_especificacoes_cto004  # noqa: E402
from batman_os.capabilities.rules.de003_loader import carregar_especificacoes_de003  # noqa: E402
from batman_os.capabilities.rules.doc004_loader import carregar_especificacoes_doc004  # noqa: E402
from batman_os.capabilities.rules.execucao_comando_interpretada_loader import (  # noqa: E402
    carregar_especificacoes_execucao_comando,
)
from batman_os.capabilities.rules.fe001_loader import carregar_especificacoes_fe001  # noqa: E402
from batman_os.capabilities.rules.fe002_loader import carregar_especificacoes_fe002  # noqa: E402
from batman_os.capabilities.rules.fe007_loader import carregar_especificacoes_fe007  # noqa: E402
from batman_os.capabilities.rules.feapi_loader import carregar_especificacoes_feapi  # noqa: E402
from batman_os.capabilities.rules.fin005_loader import carregar_especificacoes_fin005  # noqa: E402
from batman_os.capabilities.rules.git_comando_interpretado_loader import (  # noqa: E402
    carregar_especificacoes_git_interpretado,
)
from batman_os.capabilities.rules.govdebt001_loader import (  # noqa: E402
    carregar_especificacoes_govdebt001,
)
from batman_os.capabilities.rules.janela_contexto_regex_loader import (  # noqa: E402
    carregar_especificacoes_janela,
)
from batman_os.capabilities.rules.lote_01 import carregar_lote_01  # noqa: E402
from batman_os.capabilities.rules.lote_02 import carregar_lote_02  # noqa: E402
from batman_os.capabilities.rules.lote_03 import carregar_lote_03  # noqa: E402
from batman_os.capabilities.rules.metrica_com_limiar_loader import (  # noqa: E402
    carregar_especificacoes_metrica,
)
from batman_os.capabilities.rules.ora004_loader import carregar_especificacoes_ora004  # noqa: E402
from batman_os.capabilities.rules.ora005_loader import carregar_especificacoes_ora005  # noqa: E402
from batman_os.capabilities.rules.pd001_loader import carregar_especificacoes_pd001  # noqa: E402
from batman_os.capabilities.rules.pd009_loader import carregar_especificacoes_pd009  # noqa: E402
from batman_os.capabilities.rules.pd010_loader import carregar_especificacoes_pd010  # noqa: E402
from batman_os.capabilities.rules.pd011_loader import carregar_especificacoes_pd011  # noqa: E402
from batman_os.capabilities.rules.perf004_loader import (  # noqa: E402
    carregar_especificacoes_perf004,
)
from batman_os.capabilities.rules.qaauto001_loader import (  # noqa: E402
    carregar_especificacoes_qaauto001,
)
from batman_os.capabilities.rules.qaauto003_loader import (  # noqa: E402
    carregar_especificacoes_qaauto003,
)
from batman_os.capabilities.rules.regex_agregado_multi_arquivo_loader import (  # noqa: E402
    carregar_especificacoes_agregadas,
)
from batman_os.capabilities.rules.rev005_loader import carregar_especificacoes_rev005  # noqa: E402
from batman_os.capabilities.rules.rev006_loader import carregar_especificacoes_rev006  # noqa: E402
from batman_os.capabilities.rules.sec005_loader import carregar_especificacoes_sec005  # noqa: E402
from batman_os.capabilities.rules.sec007_loader import carregar_especificacoes_sec007  # noqa: E402
from batman_os.capabilities.rules.sec008_loader import carregar_especificacoes_sec008  # noqa: E402
from batman_os.capabilities.rules.sec009_loader import carregar_especificacoes_sec009  # noqa: E402
from batman_os.capabilities.rules.sre006_loader import carregar_especificacoes_sre006  # noqa: E402
from batman_os.capabilities.rules.sup001_loader import carregar_especificacoes_sup001  # noqa: E402
from batman_os.capabilities.rules.sweep001_loader import (  # noqa: E402
    carregar_especificacoes_sweep001,
)
from batman_os.capabilities.rules.toml_dependencias_loader import (  # noqa: E402
    carregar_especificacoes_dependencias,
)
from batman_os.capabilities.rules.ui002_loader import carregar_especificacoes_ui002  # noqa: E402
from batman_os.cli.scan_command import executar_scan  # noqa: E402

# Toda vez que um novo lote/Skill for migrado (Milestone 2+), adicionar seu
# carregar_*() aqui — nao ha descoberta automatica de lotes de proposito
# (mais facil de auditar o que exatamente entra na comparacao).
_TODOS_OS_ITENS = (
    carregar_lote_01()
    + carregar_lote_02()
    + carregar_lote_03()
    + carregar_especificacoes_ast()
    + carregar_especificacoes_kwarg_ausente()
    + carregar_especificacoes_git_interpretado()
    + carregar_especificacoes_execucao_comando()
    + carregar_especificacoes_dependencias()
    + carregar_especificacoes_de003()
    + carregar_especificacoes_ora005()
    + carregar_especificacoes_ora004()
    + carregar_especificacoes_agregadas()
    + carregar_especificacoes_janela()
    + carregar_especificacoes_metrica()
    + carregar_especificacoes_sup001()
    + carregar_especificacoes_sec005()
    + carregar_especificacoes_sec007()
    + carregar_especificacoes_be013()
    + carregar_especificacoes_ba004()
    + carregar_especificacoes_ba005()
    + carregar_especificacoes_arch003()
    + carregar_especificacoes_feapi()
    + carregar_especificacoes_fe001()
    + carregar_especificacoes_be010()
    + carregar_especificacoes_pd011()
    + carregar_especificacoes_qaauto001()
    + carregar_especificacoes_a11y003()
    + carregar_especificacoes_pd001()
    + carregar_especificacoes_sec009()
    + carregar_especificacoes_rev006()
    + carregar_especificacoes_govdebt001()
    + carregar_especificacoes_sweep001()
    + carregar_especificacoes_cs003()
    + carregar_especificacoes_qaauto003()
    + carregar_especificacoes_doc004()
    + carregar_especificacoes_fin005()
    + carregar_especificacoes_sec008()
    + carregar_especificacoes_pd009()
    + carregar_especificacoes_pd010()
    + carregar_especificacoes_sre006()
    + carregar_especificacoes_cs005()
    + carregar_especificacoes_cto002()
    + carregar_especificacoes_cto004()
    + carregar_especificacoes_perf004()
    + carregar_especificacoes_a11y002()
    + carregar_especificacoes_ui002()
    + carregar_especificacoes_fe002()
    + carregar_especificacoes_fe007()
    + carregar_especificacoes_rev005()
)
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
