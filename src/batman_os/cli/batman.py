"""Vol.IX Cap.34 — entry point `batman` do batman-os.

Resolve a referência declarada em `pyproject.toml`
(`batman = "batman_os.cli.batman:main"`) — antes deste módulo existir,
apontava para um caminho inexistente (confirmado por execução real,
`ModuleNotFoundError`).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from batman_os.cli.inbox_command import (
    executar_inbox_ack,
    executar_inbox_defer,
    executar_inbox_list,
    resolver_db_path_inbox,
)
from batman_os.cli.monitor_command import (
    alertas_para_inbox,
    executar_monitor,
    resolver_manifest_path,
)
from batman_os.cli.observe_command import observar_para_sempre
from batman_os.cli.scan_command import TENANT_PADRAO, achados_para_inbox, executar_scan
from batman_os.foundation.types import TenantId
from batman_os.governance.inbox import (
    AchadoInboxDesconhecido,
    AchadoInboxEntrada,
    InboxStore,
    NotaObrigatoria,
    OrigemAchado,
)

_ORDEM_SEVERIDADE = ["critical", "high", "medium", "low"]


def _severidades_a_partir_de(minimo: str) -> list[str]:
    indice = _ORDEM_SEVERIDADE.index(minimo)
    return _ORDEM_SEVERIDADE[: indice + 1]


def _resolver_db_path(root: Path, db_arg: str | None) -> str:
    """Milestone 5 desta construção — `--db` ausente usa
    `.batman-os/estado.db` relativo ao root escaneado (persistência real
    entre execuções por padrão); `--db :memory:` explícito preserva o
    comportamento efêmero anterior para quem preferir."""
    if db_arg is not None:
        return db_arg
    caminho = root / ".batman-os" / "estado.db"
    caminho.parent.mkdir(parents=True, exist_ok=True)
    return str(caminho)


def _comando_scan(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    db_path = _resolver_db_path(root, args.db)
    excluir_dirs = frozenset(args.exclude) if args.exclude else None
    resultado = executar_scan(
        root,
        db_path=db_path,
        tenant_id=TenantId(args.tenant),
        excluir_dirs=excluir_dirs,
        usar_excludes_padrao=not args.no_default_excludes,
    )

    for achado in resultado.achados:
        print(f"[{achado.severidade.upper()}] {achado.codigo} {achado.arquivo}: {achado.titulo}")

    contagem = resultado.contagem_por_severidade()
    print(f"\n{len(resultado.achados)} achado(s) — {contagem}")

    _ingerir_no_inbox_se_persistente(
        db_path,
        achados_para_inbox(resultado),
        origem=OrigemAchado.SCAN,
        tenant_id=TenantId(args.tenant),
    )

    if args.fail_on and any(
        contagem.get(severidade, 0) > 0 for severidade in _severidades_a_partir_de(args.fail_on)
    ):
        return 1
    return 0


def _ingerir_no_inbox_se_persistente(
    db_path: str | None,
    entradas: list[AchadoInboxEntrada],
    *,
    origem: OrigemAchado,
    tenant_id: TenantId,
) -> None:
    """Compartilhado por `_comando_scan`/`_comando_monitor` — grava no
    inbox (`governance/inbox.py`) quando ha um SQLite real por tras
    (`db_path` nao e `None` nem `":memory:"`). Achado de revisao fechado
    nesta construcao ("Inbox"): scan ja persiste por padrao desde a
    Milestone 5 (so ":memory:" explicito desativa); monitor NAO tinha
    `--db` nenhum antes desta construcao, entao o default dele e `None`
    (sem persistencia) -- so grava quando o operador passa `--db`
    explicitamente, preservando 100% do comportamento anterior do
    `batman monitor` por padrao."""
    if db_path is None or db_path == ":memory:":
        return
    with InboxStore(db_path) as store:
        resumo = store.ingest(entradas, origem=origem, tenant_id=tenant_id)
    print(
        f"inbox: {resumo.novos} novo(s), {resumo.atualizados} atualizado(s), "
        f"{resumo.resolvidos_automaticamente} resolvido(s) automaticamente"
    )


def _comando_monitor(args: argparse.Namespace) -> int:
    manifest_path = resolver_manifest_path(args.tenant, args.manifest)
    manifest, alertas = executar_monitor(manifest_path)

    for alerta in alertas:
        origem = alerta.evidence[0].origem if alerta.evidence else "?"
        print(f"[{alerta.severity.value.upper()}] {alerta.source.value} {origem}")

    print(f"\n{len(alertas)} alerta(s) — tenant={manifest.tenant_id}")

    _ingerir_no_inbox_se_persistente(
        args.db,
        alertas_para_inbox(alertas),
        origem=OrigemAchado.MONITOR,
        tenant_id=manifest.tenant_id,
    )
    return 0


def _comando_observe(args: argparse.Namespace) -> int:
    tenant = TenantId(args.tenant)
    ciclos = observar_para_sempre(
        tenant,
        intervalo=args.intervalo,
        max_ciclos=args.max_ciclos,
    )
    print(f"observe encerrado — {ciclos} ciclo(s), tenant={tenant}")
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
    scan_parser.add_argument(
        "--db",
        default=None,
        help=(
            "Caminho do SQLite para persistir eventos entre execucoes "
            "(default: .batman-os/estado.db relativo a --root; use ':memory:' "
            "para o comportamento efemero anterior)"
        ),
    )
    scan_parser.add_argument(
        "--tenant",
        default=str(TENANT_PADRAO),
        help=(
            "Tenant dono desta execucao (Fase 5 do roadmap de plataforma, "
            "isolamento multi-tenant; default: 'local')"
        ),
    )
    scan_parser.add_argument(
        "--exclude",
        action="append",
        default=None,
        metavar="NOME",
        help=(
            "Nome de diretorio a podar da travessia, alem dos defaults "
            "(DEFAULT_EXCLUDED_DIRS: .venv, node_modules, __pycache__, ...; "
            "ver descoberta_arquivos.py); repetivel"
        ),
    )
    scan_parser.add_argument(
        "--no-default-excludes",
        action="store_true",
        help=(
            "Escape hatch: nao aplica DEFAULT_EXCLUDED_DIRS a travessia — combine "
            "com --exclude para uma lista 100%% customizada, ou sozinho para voltar "
            "a travessia completa de antes desta mudanca"
        ),
    )
    scan_parser.set_defaults(func=_comando_scan)

    monitor_parser = subparsers.add_parser(
        "monitor",
        help=(
            "Monitor funcional sintetico: roda UM ciclo de checks das "
            "funcionalidades entregues ao usuario (para o cron de 5min)"
        ),
    )
    monitor_parser.add_argument(
        "--tenant",
        required=True,
        help="Tenant a monitorar (resolve manifests/<tenant>.json por padrao)",
    )
    monitor_parser.add_argument(
        "--manifest",
        default=None,
        help="Caminho do manifesto (default: manifests/<tenant>.json ao lado do modulo)",
    )
    monitor_parser.add_argument(
        "--db",
        default=None,
        help=(
            "Caminho do SQLite do inbox (capacidade 'Inbox', fila persistente de "
            "achados); ausente (default) = nao grava no inbox, comportamento identico "
            "ao anterior a esta capacidade"
        ),
    )
    monitor_parser.set_defaults(func=_comando_monitor)

    observe_parser = subparsers.add_parser(
        "observe",
        help=(
            "Daemon de observabilidade de infra: roda run_forever "
            "continuamente (o servico systemd batman-os-observe)"
        ),
    )
    observe_parser.add_argument(
        "--tenant",
        required=True,
        help="Tenant observado (rota os alertas via BATMAN_DISCORD_WEBHOOK_<TENANT>)",
    )
    observe_parser.add_argument(
        "--intervalo",
        type=float,
        default=60.0,
        help="Segundos entre ciclos de coleta (default: 60)",
    )
    observe_parser.add_argument(
        "--max-ciclos",
        type=int,
        default=None,
        help=(
            "Limita o numero de ciclos (execucao pontual/teste); "
            "ausente = roda indefinidamente (servico)"
        ),
    )
    observe_parser.set_defaults(func=_comando_observe)

    _montar_subparser_inbox(subparsers)

    return parser


def _montar_subparser_inbox(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Fila persistente de achados (`governance/inbox.py`) — `batman
    scan`/`batman monitor` alimentam a fila; estes subcomandos triam.
    `--db` em cada subcomando segue a MESMA convencao de default relativo
    a cwd de `resolver_db_path_inbox` (`cli/inbox_command.py`)."""
    inbox_parser = subparsers.add_parser(
        "inbox", help="Fila persistente de achados de scan/monitor"
    )
    inbox_sub = inbox_parser.add_subparsers(dest="inbox_comando", required=True)

    list_parser = inbox_sub.add_parser("list", help="Lista achados da fila (default: so 'novo')")
    list_parser.add_argument("--db", default=None, help="Caminho do SQLite do inbox")
    list_parser.add_argument(
        "--all", action="store_true", help="Mostra todos os status, nao so 'novo'"
    )
    list_parser.add_argument(
        "--tenant", default=None, help="Filtra por tenant (default: todos os tenants)"
    )
    list_parser.set_defaults(func=_comando_inbox_list)

    ack_parser = inbox_sub.add_parser("ack", help="Marca achado como TRATADO (correcao aplicada)")
    ack_parser.add_argument("id", help="Id estavel do achado (ver 'batman inbox list')")
    ack_parser.add_argument("--db", default=None, help="Caminho do SQLite do inbox")
    ack_parser.add_argument("--nota", required=True, help="Justificativa (obrigatoria)")
    ack_parser.set_defaults(func=_comando_inbox_ack)

    defer_parser = inbox_sub.add_parser(
        "defer", help="Marca achado como DEFERIDO (decisao humana de nao tratar agora)"
    )
    defer_parser.add_argument("id", help="Id estavel do achado (ver 'batman inbox list')")
    defer_parser.add_argument("--db", default=None, help="Caminho do SQLite do inbox")
    defer_parser.add_argument("--nota", required=True, help="Justificativa (obrigatoria)")
    defer_parser.set_defaults(func=_comando_inbox_defer)


def _comando_inbox_list(args: argparse.Namespace) -> int:
    db_path = resolver_db_path_inbox(args.db)
    tenant = TenantId(args.tenant) if args.tenant else None
    achados = executar_inbox_list(db_path, apenas_novos=not args.all, tenant_id=tenant)

    for achado in achados:
        print(
            f"[{achado.severidade.upper()}] {achado.id} ({achado.origem.value}/"
            f"{achado.status.value}) {achado.titulo}"
        )
    sufixo = "" if args.all else " (status=novo; use --all para ver a fila inteira)"
    print(f"\n{len(achados)} achado(s){sufixo}")
    return 0


def _comando_inbox_ack(args: argparse.Namespace) -> int:
    db_path = resolver_db_path_inbox(args.db)
    try:
        achado = executar_inbox_ack(db_path, args.id, args.nota)
    except NotaObrigatoria as exc:
        print(f"erro: {exc}")
        return 1
    except AchadoInboxDesconhecido as exc:
        print(f"erro: {exc}")
        return 1
    print(f"tratado: {achado.id} — {achado.titulo}")
    return 0


def _comando_inbox_defer(args: argparse.Namespace) -> int:
    db_path = resolver_db_path_inbox(args.db)
    try:
        achado = executar_inbox_defer(db_path, args.id, args.nota)
    except NotaObrigatoria as exc:
        print(f"erro: {exc}")
        return 1
    except AchadoInboxDesconhecido as exc:
        print(f"erro: {exc}")
        return 1
    print(f"deferido: {achado.id} — {achado.titulo}")
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = _montar_parser()
    args = parser.parse_args(argv)
    resultado: int = args.func(args)
    return resultado


if __name__ == "__main__":
    sys.exit(main())
