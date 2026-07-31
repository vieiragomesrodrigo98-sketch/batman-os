"""Entrega externa de `GovernanceAlert` (Discord) — Anexo ao Vol.VII Cap.27.

A spec original (Cap.27/Cap.30) define o ciclo INTERNO do alerta
(`registerAlertRule` -> `GovernanceAlert` -> `get_open_alerts`), mas nao
especifica entrega externa — isto e uma capacidade nova, formalizavel via
Anexo (`StatusAnexo`). Fica no plano de governanca e **nao importa
`batman_os.kernel`** (ADR-0012); recebe um `GovernanceAlert` ja pronto.

Replica o alerta Discord do Batman legado (`radar-preditivo/Batman/
observe/discord_alert.py`: embeds por severidade, retry em 429, backoff),
corrigindo os problemas achados na auditoria daquele emissor:

- **Dedupe por ESTADO, nao por cooldown fixo:** o legado reenviava o mesmo
  heartbeat "ATENCAO" com conteudo identico dias seguidos (caso ARCH-007,
  3x). Aqui, um alerta so e enviado se sua ASSINATURA de conteudo mudou
  desde o ultimo envio para o mesmo (source, tenant) — repeticao identica
  e suprimida, mudanca real passa.
- **`@everyone` contido:** o legado marcava `@everyone` para qualquer porta
  nova com bind externo. Aqui `@everyone` so ocorre para fontes numa
  allowlist explicita (default: vazia); CRITICAL usa `@here`.
- **Sem hostname cru:** o footer do legado expunha `socket.gethostname()`
  da VPS em todo embed. Aqui o footer carrega so o tenant.
- **Roteamento por tenant (ADR-0005):** webhook por `TenantId`, jamais
  vazando alerta de um tenant no canal de outro; fallback global opcional.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Protocol

from batman_os.foundation.types import TenantId
from batman_os.governance.governance_engine import (
    FonteAlerta,
    GovernanceAlert,
    SeveridadeAlerta,
)

logger = logging.getLogger(__name__)

# Discord (Cloudflare) exige um User-Agent nao-padrao (o do urllib -> 403).
_USER_AGENT = "BatmanOS-AlertSink/1.0 (+https://exemplo.test)"

# Severidade -> (cor do embed, emoji). Cores no padrao do legado.
_ESTILO: dict[SeveridadeAlerta, tuple[int, str]] = {
    SeveridadeAlerta.CRITICAL: (0xF23F43, "🔴"),
    SeveridadeAlerta.WARNING: (0xF0B232, "🟡"),
    SeveridadeAlerta.INFO: (0x58B9FF, "🔵"),
}


class AlertSink(Protocol):
    """Destino de entrega de um `GovernanceAlert`. Implementacoes NUNCA
    levantam para o chamador (best-effort — entrega falha nao pode derrubar
    o Governance Engine)."""

    def enviar(self, alert: GovernanceAlert) -> None: ...


class TransporteWebhook(Protocol):
    """Transporte HTTP injetavel (testes usam fake, sem rede)."""

    def postar(self, webhook_url: str, payload: dict[str, Any]) -> None:
        """Envia o payload; levanta em falha (o sink trata)."""
        ...


class _TransporteUrllib:
    """Transporte real via urllib (stdlib — sem dependencia nova). Trata
    HTTP 429 lendo `Retry-After` e re-tenta; backoff exponencial em erro de
    rede. Mesmo contrato de risco do `_post` legado."""

    def __init__(self, timeout: float = 10.0, max_tentativas: int = 3) -> None:
        self._timeout = timeout
        self._max_tentativas = max_tentativas

    def postar(self, webhook_url: str, payload: dict[str, Any]) -> None:
        corpo = json.dumps(payload).encode("utf-8")
        for tentativa in range(1, self._max_tentativas + 1):
            req = urllib.request.Request(
                webhook_url,
                data=corpo,
                headers={
                    "Content-Type": "application/json",
                    # A Cloudflare do Discord responde 403 ao User-Agent
                    # padrao do urllib ("Python-urllib/*"); exige um UA
                    # proprio (confirmado em campo no shadow, 2026-07-22).
                    "User-Agent": _USER_AGENT,
                },
            )
            try:
                urllib.request.urlopen(req, timeout=self._timeout).close()
                return
            except urllib.error.HTTPError as exc:
                if exc.code == 429:
                    retry_after = float(exc.headers.get("Retry-After", "1") or "1")
                    time.sleep(min(retry_after, 30.0))
                    continue
                raise  # 4xx/5xx permanente
            except (urllib.error.URLError, TimeoutError):
                if tentativa == self._max_tentativas:
                    raise
                time.sleep(2.0**tentativa)


# Linhas de evidencia VOLATEIS (medicoes que mudam todo ciclo) NAO entram na
# assinatura de dedup — senao a assinatura muda a cada envio e o throttle nunca
# dispara. Bug real (2026-07-23): feature-down re-alertava a cada 5min porque a
# evidencia trazia `latencia=91.7ms`, diferente em cada ciclo. A IDENTIDADE do
# alerta e o que ele E (feature/status/porta), nao quanto tempo levou.
_EVIDENCIA_VOLATIL = re.compile(
    r"^\s*(lat[êe]ncia|latency|dura[çc][ãa]o|tempo|rtt|p50|p95|uptime|"
    r"observed_at|timestamp|\bts\b|corpo\[|ciclo|batimento)",
    re.I,
)


def _assinatura(alert: GovernanceAlert) -> str:
    """Assinatura de CONTEUDO (nao inclui o id uuid7, sempre unico, NEM campos
    volateis como latencia/timestamp) — base do dedupe por estado."""
    partes = [
        alert.source.value,
        alert.severity.value,
        str(alert.related_tenant_id or ""),
    ]
    for ev in alert.evidence:
        partes.append(ev.origem)
        partes.extend(e for e in ev.evidencias if not _EVIDENCIA_VOLATIL.match(e))
    return "\n".join(partes)


# Roteamento por TEMA: cada fonte de alerta -> nome de canal (reusa os
# canais existentes do legado: security/infra/performance/log). Fonte sem
# entrada aqui cai no `canal_padrao` ("o que mais se aproxima"). Espelha o
# `RULE_CHANNEL` do `discord_alert.py` legado.
CANAL_POR_FONTE: dict[FonteAlerta, str] = {
    FonteAlerta.INFRA_SATURATION: "infra",
    FonteAlerta.SERVICE_DOWN: "infra",
    FonteAlerta.ENDPOINT_DOWN: "performance",
    FonteAlerta.ENDPOINT_LATENCY: "performance",
    FonteAlerta.ENDPOINT_ERROR_RATE: "performance",
    FonteAlerta.FEATURE_DOWN: "performance",
    FonteAlerta.FEATURE_RECOVERED: "performance",
    FonteAlerta.SLA_BREACH: "performance",
    FonteAlerta.SECURITY_INTRUSION: "security",
    FonteAlerta.TENANT_ISOLATION_INCIDENT: "security",
    FonteAlerta.OBSERVE_HEARTBEAT: "log",
    FonteAlerta.MANIFEST_DRIFT: "log",
    FonteAlerta.LLM_CIRCUIT_BREAKER: "log",
    FonteAlerta.RULE_DRIFT: "log",
    FonteAlerta.HUMAN_REVIEW_BACKLOG: "log",
    FonteAlerta.ADDENDUM_REVIEW_REQUEST: "log",
}


class DiscordAlertSink:
    """Satisfaz `AlertSink`. Constroi o embed, aplica dedupe por estado e
    roteia por TEMA (fonte->canal, `CANAL_POR_FONTE`) quando ha
    `webhooks_por_canal`; senao roteia por tenant. Nunca levanta em
    `enviar`."""

    def __init__(
        self,
        webhooks_por_tenant: dict[TenantId, str] | None = None,
        webhook_global: str | None = None,
        transporte: TransporteWebhook | None = None,
        fontes_everyone: frozenset[FonteAlerta] = frozenset(),
        webhooks_por_canal: dict[str, str] | None = None,
        canal_padrao: str = "log",
        caminho_estado: Path | None = None,
        janela_repeticao_s: float = 86400.0,
        janelas_por_severidade: dict[SeveridadeAlerta, float] | None = None,
    ) -> None:
        self._webhooks = dict(webhooks_por_tenant or {})
        self._webhook_global = webhook_global
        self._transporte: TransporteWebhook = transporte or _TransporteUrllib()
        self._fontes_everyone = fontes_everyone
        self._webhooks_por_canal = dict(webhooks_por_canal or {})
        self._canal_padrao = canal_padrao
        # Dedupe por estado com JANELA (default 24h): (source|tenant) ->
        # {"sig": assinatura, "ts": epoch}. Reenvia se a assinatura MUDOU
        # (transicao real — nova falha OU recuperacao) OU se passou a janela
        # desde o ultimo envio identico. Um alerta CONHECIDO e REPETIDO (ex.:
        # feature caida sob incidente ativo) vira no maximo 1x/dia, em vez de
        # 1x a cada ciclo de 5min. PERSISTIDO em disco: cada run do cron do
        # monitor e um processo NOVO — sem disco, o estado nascia vazio e
        # re-alertava todo ciclo (o flood que o Rodrigo reportou, 2026-07-23).
        self._caminho_estado = caminho_estado
        self._janela_repeticao_s = janela_repeticao_s
        # Janela de re-alerta POR SEVERIDADE (diretriz do Rodrigo, 2026-07-24):
        # so faz sentido re-alertar de HORA EM HORA o que impacta o usuario /
        # derruba feature / e vulnerabilidade (CRITICAL). WARNING espaca mais;
        # INFO/telemetria (heartbeat, porta loopback benigna) vira 1x/dia.
        self._janelas: dict[SeveridadeAlerta, float] = janelas_por_severidade or {
            SeveridadeAlerta.CRITICAL: 3600.0,    # 1h — outage/vulnerabilidade ATIVA
            SeveridadeAlerta.WARNING: 21600.0,    # 6h
            SeveridadeAlerta.INFO: 86400.0,       # 24h — telemetria/benigno
        }
        self._janela_maxima = max(self._janelas.values(), default=janela_repeticao_s)
        self._estado: dict[str, dict[str, Any]] = self._carregar_estado()

    def _carregar_estado(self) -> dict[str, dict[str, Any]]:
        """Le o estado persistido (best-effort), podando entradas mais velhas
        que a janela — mantem o arquivo pequeno e uma leitura corrompida nunca
        derruba a entrega (comeca limpo)."""
        if self._caminho_estado is None or not self._caminho_estado.exists():
            return {}
        try:
            dados = json.loads(self._caminho_estado.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("estado de dedup ilegivel (%s), comecando limpo: %s",
                           self._caminho_estado, exc)
            return {}
        agora = time.time()
        return {
            k: v for k, v in dados.items()
            if isinstance(v, dict) and isinstance(v.get("ts"), (int, float))
            and (agora - float(v["ts"])) < self._janela_maxima
        }

    def _persistir_estado(self) -> None:
        """Grava o estado atomicamente (tmp + replace) — best-effort, uma
        falha de I/O nunca derruba o Governance Engine."""
        if self._caminho_estado is None:
            return
        try:
            self._caminho_estado.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._caminho_estado.with_suffix(self._caminho_estado.suffix + ".tmp")
            tmp.write_text(json.dumps(self._estado), encoding="utf-8")
            tmp.replace(self._caminho_estado)
        except OSError as exc:
            logger.warning("falha ao persistir estado de dedup: %s", exc)

    def _webhook_para(self, alert: GovernanceAlert) -> str | None:
        # 1) roteamento por tema (fonte -> canal -> webhook), com fallback
        #    para o canal padrao ("o que mais se aproxima").
        if self._webhooks_por_canal:
            canal = CANAL_POR_FONTE.get(alert.source, self._canal_padrao)
            webhook = self._webhooks_por_canal.get(canal) or self._webhooks_por_canal.get(
                self._canal_padrao
            )
            if webhook:
                return webhook
        # 2) fallback: por tenant, depois global.
        tenant = alert.related_tenant_id
        if tenant is not None and tenant in self._webhooks:
            return self._webhooks[tenant]
        return self._webhook_global

    def _mention(self, alert: GovernanceAlert) -> str:
        if alert.severity is SeveridadeAlerta.CRITICAL:
            return "@everyone" if alert.source in self._fontes_everyone else "@here"
        return ""

    def _payload(self, alert: GovernanceAlert) -> dict[str, Any]:
        cor, emoji = _ESTILO[alert.severity]
        campos: list[dict[str, Any]] = []
        for ev in alert.evidence:
            valor = "\n".join(ev.evidencias) if ev.evidencias else "(sem detalhe)"
            if ev.confianca is not None:
                valor += f"\n_confianca: {ev.confianca:.2f}_"
            campos.append({"name": ev.origem[:256], "value": valor[:1024], "inline": False})
        tenant = str(alert.related_tenant_id or "global")
        return {
            "content": self._mention(alert),
            "embeds": [
                {
                    "title": f"{emoji} [{alert.severity.value.upper()}] {alert.source.value}",
                    "color": cor,
                    "fields": campos,
                    "footer": {"text": f"Batman OS · Governance · tenant={tenant}"},
                }
            ],
        }

    def enviar(self, alert: GovernanceAlert) -> None:
        webhook = self._webhook_para(alert)
        if webhook is None:
            return  # sem canal para este tenant — no-op silencioso (como o legado)

        # Chave = hash da ASSINATURA COMPLETA (source+severidade+tenant+toda a
        # evidencia), NAO (source,tenant): dois alertas do MESMO source no mesmo
        # ciclo (ex.: portas 5678 e 5679, ambos security-intrusion) tem chaves
        # DISTINTAS e cada um throttla sozinho — senao se sobrescreviam e ambos
        # re-disparavam todo ciclo (a causa real do flood duplo, 2026-07-23).
        chave = hashlib.sha256(_assinatura(alert).encode("utf-8")).hexdigest()[:16]
        agora = time.time()
        anterior = self._estado.get(chave)
        janela = self._janelas.get(alert.severity, self._janela_repeticao_s)
        idade = agora - float(anterior["ts"]) if anterior else None
        if idade is not None and idade < janela:
            logger.debug("alerta repetido suprimido (throttle %.0fs, sev=%s): %s",
                         janela, alert.severity.value, chave)
            return

        try:
            self._transporte.postar(webhook, self._payload(alert))
        except Exception as exc:  # entrega best-effort, jamais derruba governanca
            logger.error("falha ao entregar GovernanceAlert no Discord: %s", exc)
            return
        # so marca como enviado apos sucesso — falha permite reenvio no proximo
        self._estado[chave] = {"ts": agora}
        self._persistir_estado()
