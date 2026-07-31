"""Vol.IX Cap.34 — orquestrador do `batman observe` (daemon de infra).

Fecha o gap do daemon que faltava: o legado rodava um `batman-observe.service`
(systemd, `Restart=always`) que observava CPU/RAM/disco/portas/logs/processos
continuamente; o Batman OS ja tinha o motor (`observe/watcher.py::ObserveWatcher`)
mas nenhuma borda de CLI ligando os coletores reais a ele. Este modulo e essa
borda.

Duas superficies, mesmo wiring:

- `executar_observe(...)` — roda UM ciclo (`ObserveWatcher.run_once`). E a
  funcao testavel, com as BORDAS injetaveis (coletores + governance) — os
  testes passam fakes e rodam sem rede/psutil (mesmo estilo de
  `monitor_command.executar_monitor`).
- `observar_para_sempre(...)` — roda `ObserveWatcher.run_forever` continuamente.
  E o corpo do servico systemd (`deploy/batman-os-observe.service`).

Best-effort e psutil-opcional (contrato de paridade do subsistema `observe`):
os coletores reais ja degradam para amostras vazias quando psutil falta
(`observe/collectors.py`), e a montagem do snapshot aqui envolve cada coleta
num guarda extra — um coletor que LEVANTA e logado e o ciclo continua, nunca
derruba o daemon. O `run_forever` do watcher tambem engole excecao por ciclo.

Roteamento de alerta por tenant (ADR-0005): o `related_tenant_id` de todo
alerta e o tenant do arg — o snapshot carrega `tenant_id`, e cada regra de
observacao o propaga para o alerta. O sink (Discord) roteia por esse tenant.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import partial
from typing import TypeVar

from batman_os.cli.monitor_command import sink_do_ambiente
from batman_os.foundation.types import TenantId
from batman_os.governance.governance_engine import GovernanceAlert, GovernanceEngine
from batman_os.observe.collectors import (
    EndpointCollectorComoAssinatura,
    EndpointCollectorUrllib,
    InfraCollectorComoAssinatura,
    InfraCollectorPsutil,
    LogCollectorComoAssinatura,
    LogCollectorTail,
    PortCollectorComoAssinatura,
    PortCollectorPsutil,
    ProcessCollectorComoAssinatura,
    ProcessCollectorPsutil,
)
from batman_os.observe.snapshot import AmostraEndpoint, ObserveSnapshot
from batman_os.observe.watcher import (
    DormirComoAssinatura,
    EventoDeParadaComoAssinatura,
    ObserveWatcher,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class Coletores:
    """As cinco bordas reais de coleta de um ciclo de observacao. Agrupadas
    num so objeto para o wiring passar/injetar de uma vez (testes montam
    fakes que satisfazem os mesmos Protocols de `observe/collectors.py`)."""

    infra: InfraCollectorComoAssinatura
    endpoint: EndpointCollectorComoAssinatura
    portas: PortCollectorComoAssinatura
    log: LogCollectorComoAssinatura
    processo: ProcessCollectorComoAssinatura


def montar_coletores() -> Coletores:
    """Coletores REAIS da VPS (psutil para infra/portas/processos, urllib
    stdlib para endpoints, tail de arquivo para nginx/auth). psutil e
    dependencia OPCIONAL (extra `observe`): as impls degradam para amostras
    vazias quando ela falta — o daemon nunca quebra por isso."""
    return Coletores(
        infra=InfraCollectorPsutil(),
        endpoint=EndpointCollectorUrllib(headers_hardening=None),
        portas=PortCollectorPsutil(),
        log=LogCollectorTail(),
        processo=ProcessCollectorPsutil(),
    )


def endpoints_do_ambiente(tenant_id: TenantId) -> list[str]:
    """URLs de endpoint a sondar por ciclo, do env
    `BATMAN_OBSERVE_ENDPOINTS_<TENANT>` (separadas por virgula). Ausente =>
    lista vazia: o daemon observa infra/portas/logs/processos sem probe HTTP
    (degrada, nao quebra)."""
    bruto = os.environ.get(f"BATMAN_OBSERVE_ENDPOINTS_{tenant_id.upper()}", "")
    return [u.strip() for u in bruto.split(",") if u.strip()]


def processos_esperados_do_ambiente(tenant_id: TenantId) -> list[str]:
    """Nomes de processo que DEVEM estar rodando (health de servico), do env
    `BATMAN_OBSERVE_PROCESSOS_<TENANT>` (separados por virgula). Ausente =>
    lista vazia: sem check de servico-caido (config, nao outage)."""
    bruto = os.environ.get(f"BATMAN_OBSERVE_PROCESSOS_{tenant_id.upper()}", "")
    return [p.strip() for p in bruto.split(",") if p.strip()]


def _coleta_opcional(fn: Callable[[], T], descricao: str) -> T | None:
    """Roda uma coleta best-effort: um coletor que levanta e logado e vira
    `None` (a `watch_rule` correspondente trata `None` como 'nao coletado' e
    silencia). Defesa em profundidade sobre o degrade que os coletores reais
    ja fazem internamente."""
    try:
        return fn()
    except Exception as exc:  # best-effort: coletor ruim nao derruba o ciclo
        logger.warning("coletor '%s' falhou (best-effort, ciclo continua): %s", descricao, exc)
        return None


def _coleta_lista(fn: Callable[[], list[str]], descricao: str) -> list[str]:
    """Como `_coleta_opcional`, mas para coletas que devolvem lista (default
    seguro = lista vazia)."""
    try:
        return fn()
    except Exception as exc:  # best-effort
        logger.warning("coletor '%s' falhou (best-effort, ciclo continua): %s", descricao, exc)
        return []


def coletar_snapshot(
    tenant_id: TenantId,
    coletores: Coletores,
    *,
    urls_endpoints: Sequence[str] = (),
    processos_esperados: Sequence[str] = (),
) -> ObserveSnapshot:
    """Funcao coletora: monta o `ObserveSnapshot` de UM ciclo a partir das
    bordas reais. Cada coleta e best-effort (ver `_coleta_opcional`). O
    snapshot carrega `tenant_id` para que todo alerta derivado herde o tenant
    (roteamento do sink, ADR-0005)."""
    endpoints: list[AmostraEndpoint] = []
    for url in urls_endpoints:
        amostra = _coleta_opcional(partial(coletores.endpoint.coletar, url), f"endpoint:{url}")
        if amostra is not None:
            endpoints.append(amostra)
    return ObserveSnapshot(
        tenant_id=tenant_id,
        infra=_coleta_opcional(coletores.infra.coletar, "infra"),
        endpoints=endpoints,
        portas=_coleta_opcional(coletores.portas.coletar, "portas"),
        processos_rodando=_coleta_lista(coletores.processo.coletar, "processos"),
        processos_esperados=list(processos_esperados),
        nginx=_coleta_opcional(coletores.log.coletar_nginx, "nginx"),
        auth=_coleta_opcional(coletores.log.coletar_auth, "auth"),
    )


def _montar_watcher(tenant_id: TenantId, governance: GovernanceEngine | None) -> ObserveWatcher:
    """Monta o `ObserveWatcher` com o `GovernanceEngine` do wiring. Sem
    `governance`, monta um com o sink do ambiente (Discord por tenant, mesmo
    padrao de `monitor_command`)."""
    if governance is None:
        governance = GovernanceEngine(sink=sink_do_ambiente(tenant_id))
    return ObserveWatcher(
        governance, tenant_id=tenant_id, ciclos_por_heartbeat=_ciclos_por_heartbeat()
    )


def _ciclos_por_heartbeat() -> int:
    """Frequencia do batimento "watcher=vivo", em CICLOS. Default 1440 — com o
    intervalo de 60s do servico, isso e 1 batimento por DIA (antes era 60 = de
    hora em hora, o que floodava o Discord). Ajustavel sem redeploy via
    `BATMAN_OBSERVE_HEARTBEAT_CICLOS` (ex.: 1440=diario, 10080=semanal)."""
    try:
        return max(1, int(os.environ.get("BATMAN_OBSERVE_HEARTBEAT_CICLOS", "1440")))
    except ValueError:
        return 1440


def executar_observe(
    tenant_id: TenantId,
    *,
    coletores: Coletores | None = None,
    urls_endpoints: Sequence[str] | None = None,
    processos_esperados: Sequence[str] | None = None,
    governance: GovernanceEngine | None = None,
) -> list[GovernanceAlert]:
    """Roda UM ciclo de observacao (coleta -> `run_once` -> entrega via sink).
    Todas as bordas sao injetaveis (testes usam fakes, sem rede/psutil):

    - `coletores` ausente => coletores reais (`montar_coletores`).
    - `urls_endpoints`/`processos_esperados` ausentes (None) => lidos do
      ambiente por tenant; uma lista explicita (mesmo vazia) e usada como esta.
    - `governance` ausente => `GovernanceEngine` com o sink do ambiente.

    Retorna os `GovernanceAlert` do ciclo (ja entregues pelo `run_once`)."""
    coletores = coletores or montar_coletores()
    if urls_endpoints is None:
        urls_endpoints = endpoints_do_ambiente(tenant_id)
    if processos_esperados is None:
        processos_esperados = processos_esperados_do_ambiente(tenant_id)
    watcher = _montar_watcher(tenant_id, governance)
    snapshot = coletar_snapshot(
        tenant_id,
        coletores,
        urls_endpoints=urls_endpoints,
        processos_esperados=processos_esperados,
    )
    return watcher.run_once(snapshot)


def observar_para_sempre(
    tenant_id: TenantId,
    *,
    intervalo: float,
    coletores: Coletores | None = None,
    urls_endpoints: Sequence[str] | None = None,
    processos_esperados: Sequence[str] | None = None,
    governance: GovernanceEngine | None = None,
    max_ciclos: int | None = None,
    parar: EventoDeParadaComoAssinatura | None = None,
    dormir: DormirComoAssinatura | None = None,
) -> int:
    """O daemon systemd: roda `ObserveWatcher.run_forever` — coleta um snapshot
    e roda um ciclo a cada `intervalo` segundos, best-effort (uma excecao num
    ciclo e logada e o loop CONTINUA). Mesmo wiring de `executar_observe`,
    reusando a funcao coletora a cada ciclo.

    `max_ciclos`/`parar`/`dormir` sao para execucoes limitadas e testes (rodar
    N ciclos sem `time.sleep` real); ausentes, roda indefinidamente. Retorna o
    numero de ciclos rodados."""
    coletores = coletores or montar_coletores()
    if urls_endpoints is None:
        urls_endpoints = endpoints_do_ambiente(tenant_id)
    if processos_esperados is None:
        processos_esperados = processos_esperados_do_ambiente(tenant_id)
    watcher = _montar_watcher(tenant_id, governance)

    def coletar() -> ObserveSnapshot:
        return coletar_snapshot(
            tenant_id,
            coletores,
            urls_endpoints=urls_endpoints,
            processos_esperados=processos_esperados,
        )

    return watcher.run_forever(
        intervalo, coletar, max_ciclos=max_ciclos, parar=parar, dormir=dormir
    )
