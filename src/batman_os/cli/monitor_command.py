"""Vol.IX Cap.34 — orquestrador do `batman monitor` (monitor funcional).

Roda UM ciclo (`FunctionalMonitor.run_once`) sobre o manifesto de um tenant —
o formato pensado para o cron de 5min do VPS (paridade com `batman patrol` do
legado, que ja roda por cron). `run_forever` existe no `FunctionalMonitor` para
quem preferir rodar como servico.

Como o `scan_command`, expoe uma funcao testavel (`executar_monitor`) com as
bordas de I/O injetaveis (sonda + credenciais) para os testes rodarem SEM rede.
O webhook do Discord vem do ambiente (roteamento por tenant, ADR-0005); sem
webhook, os alertas so vivem em memoria e sao impressos.
"""

from __future__ import annotations

import os
from pathlib import Path

from batman_os.foundation.types import TenantId
from batman_os.governance.alert_sinks import DiscordAlertSink
from batman_os.governance.governance_engine import GovernanceAlert, GovernanceEngine
from batman_os.governance.inbox import AchadoInboxEntrada, mapear_severidade_alerta
from batman_os.observe.data_manifest import (
    DataSentinelManifest,
    caminho_manifesto_dados,
    carregar_manifesto_dados,
)
from batman_os.observe.data_sentinela import DataSentinelMonitor
from batman_os.observe.feature_manifest import (
    FeatureManifest,
    caminho_manifesto,
    carregar_manifesto,
)
from batman_os.observe.functional_monitor import (
    FunctionalMonitor,
    ProvedorCredenciaisComoAssinatura,
    SondadorComoAssinatura,
)


def resolver_manifest_path(tenant_id: str, manifest_arg: str | None) -> Path:
    """`--manifest` explicito vence; senao usa `manifests/<tenant>.json`."""
    if manifest_arg is not None:
        return Path(manifest_arg)
    return caminho_manifesto(tenant_id)


_CANAIS = ("security", "infra", "performance", "log")


def sink_do_ambiente(tenant_id: TenantId) -> DiscordAlertSink | None:
    """Monta o `DiscordAlertSink` a partir do ambiente. Prioriza roteamento
    por TEMA: `BATMAN_DISCORD_WEBHOOK_CANAL_<CANAL>` (security/infra/
    performance/log) reusa os canais do legado, com o sink escolhendo o
    canal por fonte de alerta. Fallback: `BATMAN_DISCORD_WEBHOOK_<TENANT>`
    (por tenant) e `BATMAN_DISCORD_WEBHOOK` (global). Sem nada definido,
    retorna `None` (alertas so em memoria) — nunca ha webhook no repo."""
    por_canal = {
        canal: url
        for canal in _CANAIS
        if (url := os.environ.get(f"BATMAN_DISCORD_WEBHOOK_CANAL_{canal.upper()}"))
    }
    especifico = os.environ.get(f"BATMAN_DISCORD_WEBHOOK_{tenant_id.upper()}")
    glob = os.environ.get("BATMAN_DISCORD_WEBHOOK")
    if not por_canal and not especifico and not glob:
        return None
    webhooks = {tenant_id: especifico} if especifico else {}
    # Estado de dedup persistido (throttle diario) — sobrevive ao processo-frio
    # do cron. `BATMAN_ALERT_DEDUP_PATH` sobrescreve; default relativo ao cwd
    # (o run_monitor.sh/run_observe.sh fazem `cd /opt/batman-os`, entao
    # monitor e observe COMPARTILHAM o mesmo arquivo). `BATMAN_ALERT_JANELA_S`
    # ajusta a janela (default 86400 = 1x/dia).
    caminho_env = os.environ.get("BATMAN_ALERT_DEDUP_PATH")
    caminho_estado = Path(caminho_env) if caminho_env else Path(".batman-os") / "alert_dedup.json"
    janela = float(os.environ.get("BATMAN_ALERT_JANELA_S", "86400"))
    return DiscordAlertSink(
        webhooks_por_tenant=webhooks,
        webhook_global=glob,
        webhooks_por_canal=por_canal,
        caminho_estado=caminho_estado,
        janela_repeticao_s=janela,
    )


def resolver_manifest_dados_path(tenant_id: str, manifest_arg: str | None) -> Path:
    """Mesmo espírito de `resolver_manifest_path` para o manifesto de
    dados (capability `dados-sentinela`): `--dados-manifest` explícito
    vence; senão usa `manifests/<tenant>_dados.json`."""
    if manifest_arg is not None:
        return Path(manifest_arg)
    return caminho_manifesto_dados(tenant_id)


def executar_dados_sentinela(
    manifest_path: str | Path,
    *,
    root_dir_override: str | None = None,
    governance: GovernanceEngine | None = None,
) -> tuple[DataSentinelManifest, list[GovernanceAlert]]:
    """Carrega o manifesto de dados e roda um ciclo (`DataSentinelMonitor.
    run_once`). `root_dir_override` sobrescreve `DataSentinelManifest.
    root_dir` sem precisar editar o manifesto (útil em teste e para apontar
    o mesmo manifesto para staging/prod via `--dados-root`). Sem
    `governance`, monta um `GovernanceEngine` com o sink do ambiente
    (Discord por tenant/canal, mesmo `sink_do_ambiente` do `batman monitor`
    HTTP — reusa o MESMO roteamento/dedupe, nenhum mecanismo paralelo)."""
    manifest = carregar_manifesto_dados(manifest_path)
    if root_dir_override is not None:
        manifest = manifest.model_copy(update={"root_dir": root_dir_override})
    if governance is None:
        governance = GovernanceEngine(sink=sink_do_ambiente(manifest.tenant_id))
    monitor = DataSentinelMonitor(governance)
    alertas = monitor.run_once(manifest)
    return manifest, alertas


def alertas_para_inbox(alertas: list[GovernanceAlert]) -> list[AchadoInboxEntrada]:
    """Adaptador `GovernanceAlert` -> `AchadoInboxEntrada` (`governance/
    inbox.py`, capacidade "Inbox" de fila persistente de achados). Vive
    AQUI, não em `governance/inbox.py`, pelo mesmo motivo do adaptador
    irmão em `cli/scan_command.py::achados_para_inbox` — `governance/`
    nunca importa de `cli/`, mas `GovernanceAlert` já é um tipo de
    `governance/`, então este adaptador podia viver lá também; fica aqui
    por coesão com o resto do wiring do `batman monitor`.

    `chave_dominio` = `source|alvo` — `alvo` é `evidence[0].origem`
    (convenção já usada por todo `GovernanceAlert` deste subsistema, ex.:
    `f"feature-monitor:{check.id}"` em `observe/functional_monitor.py`);
    um alerta sem evidência (nunca deveria acontecer — `Evidence First`,
    AT-8.1 do Decision Engine) cai em `"sem-evidencia"` em vez de
    levantar, para o monitor nunca quebrar por causa do inbox."""
    return [
        AchadoInboxEntrada(
            chave_dominio=(
                f"{alerta.source.value}|"
                f"{alerta.evidence[0].origem if alerta.evidence else 'sem-evidencia'}"
            ),
            severidade=mapear_severidade_alerta(alerta.severity),
            titulo=f"{alerta.source.value}: {alerta.evidence[0].origem if alerta.evidence else ''}",
            detalhe="; ".join(evidencia for ev in alerta.evidence for evidencia in ev.evidencias)
            or alerta.source.value,
        )
        for alerta in alertas
    ]


def executar_monitor(
    manifest_path: str | Path,
    *,
    sondador: SondadorComoAssinatura | None = None,
    credenciais: ProvedorCredenciaisComoAssinatura | None = None,
    governance: GovernanceEngine | None = None,
) -> tuple[FeatureManifest, list[GovernanceAlert]]:
    """Carrega o manifesto e roda um ciclo. `sondador`/`credenciais`/`governance`
    injetaveis (testes usam fakes, sem rede). Sem `governance`, monta um
    `GovernanceEngine` com o sink do ambiente (Discord por tenant)."""
    manifest = carregar_manifesto(manifest_path)
    if governance is None:
        governance = GovernanceEngine(sink=sink_do_ambiente(manifest.tenant_id))
    monitor = FunctionalMonitor(governance, sondador=sondador, credenciais=credenciais)
    alertas = monitor.run_once(manifest)
    return manifest, alertas
