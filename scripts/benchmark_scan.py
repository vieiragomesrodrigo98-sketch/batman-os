"""Benchmark de performance do scan (Fase 1 do roadmap de plataforma,
item "Performance" — `.claude/plans/peaceful-wondering-hearth.md`).

Roda `executar_scan` contra um repositório real e reporta o tempo total
por Capability, ordenado do mais lento para o mais rápido. Não adiciona
instrumentação nova: reaproveita `StepResult.iniciado_em`/`finalizado_em`,
já medido nativamente pelo Workflow Engine (Vol.II Cap.9) para cada
step — este script só agrega e apresenta (`ResultadoScan.
resumo_de_performance()`, `cli/scan_command.py`).

Planning/Decision não entram no relatório: neste fluxo (regra
determinística, `_LlmNuncaChamadoNesteFluxo`/`_SemConhecimentoAinda`,
`cli/scan_command.py`) as duas fases nunca fazem trabalho real — o custo
inteiro está na execução da Capability (IO de arquivo + avaliação de
regex/AST). Medir Planning/Decision aqui seria relatar ruído, não sinal.

Uso:
    python scripts/benchmark_scan.py --root <caminho> [--top N]
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from batman_os.cli.scan_command import executar_scan  # noqa: E402


def _imprimir_relatorio(
    duracao_total_s: float, achados: int, resumo: dict[str, dict[str, float]], top: int
) -> None:
    print(f"Scan completo em {duracao_total_s:.2f}s — {achados} achado(s)\n")
    if not resumo:
        print("(nenhuma Capability mediu tempo — repositorio sem arquivos candidatos?)")
        return

    ordenado = sorted(resumo.items(), key=lambda item: item[1]["total_ms"], reverse=True)
    cabecalho = (
        f"{'Capability':<45} {'chamadas':>9} {'total_ms':>10} {'media_ms':>10} {'max_ms':>10}"
    )
    print(cabecalho)
    print("-" * len(cabecalho))
    for capability_id, stats in ordenado[:top]:
        print(
            f"{capability_id:<45} {stats['chamadas']:>9.0f} {stats['total_ms']:>10.1f} "
            f"{stats['media_ms']:>10.2f} {stats['max_ms']:>10.1f}"
        )
    if len(ordenado) > top:
        print(f"... e mais {len(ordenado) - top} Capability(s) (use --top para ver todas)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--top", type=int, default=20)
    args = parser.parse_args(argv)

    inicio = time.perf_counter()
    resultado = executar_scan(args.root.resolve())
    duracao_total_s = time.perf_counter() - inicio

    _imprimir_relatorio(
        duracao_total_s, len(resultado.achados), resultado.resumo_de_performance(), args.top
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
