"""Vol.IX Cap.34 — entry point `batman` do batman-os.

Resolve a referência declarada em `pyproject.toml`
(`batman = "batman_os.cli.batman:main"`) — antes deste módulo existir,
apontava para um caminho inexistente (confirmado por execução real,
`ModuleNotFoundError`).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from batman_os.cli.scan_command import executar_scan

_ORDEM_SEVERIDADE = ["critical", "high", "medium", "low"]


def _severidades_a_partir_de(minimo: str) -> list[str]:
    indice = _ORDEM_SEVERIDADE.index(minimo)
    return _ORDEM_SEVERIDADE[: indice + 1]


def _comando_scan(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    resultado = executar_scan(root)

    for achado in resultado.achados:
        print(f"[{achado.severidade.upper()}] {achado.codigo} {achado.arquivo}: {achado.titulo}")

    contagem = resultado.contagem_por_severidade()
    print(f"\n{len(resultado.achados)} achado(s) — {contagem}")

    if args.fail_on and any(
        contagem.get(severidade, 0) > 0 for severidade in _severidades_a_partir_de(args.fail_on)
    ):
        return 1
    return 0


def _montar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="batman")
    subparsers = parser.add_subparsers(dest="comando", required=True)

    scan_parser = subparsers.add_parser(
        "scan", help="Roda o primeiro lote de Capabilities migradas contra um repositorio"
    )
    scan_parser.add_argument("--root", default=".", help="Raiz do repositorio alvo")
    scan_parser.add_argument(
        "--fail-on",
        choices=_ORDEM_SEVERIDADE,
        default=None,
        help="Retorna codigo de saida 1 se houver achado nesta severidade ou mais grave",
    )
    scan_parser.set_defaults(func=_comando_scan)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _montar_parser()
    args = parser.parse_args(argv)
    resultado: int = args.func(args)
    return resultado


if __name__ == "__main__":
    sys.exit(main())
