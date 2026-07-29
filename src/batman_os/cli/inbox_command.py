"""Vol.IX Cap.34 — orquestrador do `batman inbox` (fila persistente de
achados, `governance/inbox.py`).

Mesmo padrão dos demais orquestradores de CLI (`scan_command.py`,
`monitor_command.py`): funções testáveis (`executar_inbox_*`) com a única
borda de I/O (o `InboxStore`, sobre o SQLite de `--db`) isolada — `cli/
batman.py` só faz o parsing de argparse e o `print` do resultado.
"""

from __future__ import annotations

from pathlib import Path

from batman_os.foundation.types import TenantId
from batman_os.governance.inbox import AchadoInbox, InboxStore

CAMINHO_DB_PADRAO = Path(".batman-os") / "estado.db"


def resolver_db_path_inbox(db_arg: str | None) -> str:
    """`--db` explícito vence; senão usa `.batman-os/estado.db` relativo
    ao diretório de trabalho atual — mesmo default relativo-a-cwd já usado
    por `governance/alert_sinks.py::sink_do_ambiente` (o dedup do Discord),
    e não relativo a um `--root` (o `batman inbox` não escaneia um
    repositório, só consulta a fila já persistida). Em produção, o cron do
    VPS já faz `cd /opt/batman-os` antes de rodar `scan`/`monitor`
    (ver comentário em `monitor_command.py::sink_do_ambiente`) — rodando
    `batman inbox` do mesmo diretório, os três comandos compartilham o
    MESMO arquivo `.batman-os/estado.db`."""
    if db_arg is not None:
        return db_arg
    CAMINHO_DB_PADRAO.parent.mkdir(parents=True, exist_ok=True)
    return str(CAMINHO_DB_PADRAO)


def executar_inbox_list(
    db_path: str, *, apenas_novos: bool = True, tenant_id: TenantId | None = None
) -> list[AchadoInbox]:
    with InboxStore(db_path) as store:
        return store.listar(apenas_novos=apenas_novos, tenant_id=tenant_id)


def executar_inbox_ack(db_path: str, achado_id: str, nota: str) -> AchadoInbox:
    """Marca `TRATADO` (correção aplicada). Levanta `NotaObrigatoria` se
    `nota` for vazia/só espaços, `AchadoInboxDesconhecido` se `achado_id`
    não existir na fila (ver `governance/inbox.py::InboxStore.ack`)."""
    with InboxStore(db_path) as store:
        return store.ack(achado_id, nota)


def executar_inbox_defer(db_path: str, achado_id: str, nota: str) -> AchadoInbox:
    """Marca `DEFERIDO` (decisão humana explícita de não tratar agora —
    doutrina "zero débito: só o humano defere"). Mesmas exceções de
    `executar_inbox_ack`."""
    with InboxStore(db_path) as store:
        return store.defer(achado_id, nota)
