"""Collectors de observabilidade — Protocols injetaveis + impls reais.

Anexo ao Vol.VII Cap.27/30 (subsistema `batman_os.observe`). Espelha o
`observe/collector.py` do Batman legado, mas cada collector expoe um
Protocol "…ComoAssinatura" (mesmo padrao de `_ClienteAnthropicComoAssinatura`
em `llm/anthropic_gateway.py`) para que os testes injetem fakes SEM I/O
real — zero psutil/rede no CI.

`psutil` e dependencia OPCIONAL (extra `observe`); as impls reais degradam
para amostras vazias quando ela falta, nunca levantam (best-effort, como o
`_psutil()` legado).
"""

from __future__ import annotations

import logging
import re
import time
import urllib.error
import urllib.request
from collections import Counter
from typing import TYPE_CHECKING, Any, Protocol

from batman_os.observe.snapshot import (
    AmostraAuth,
    AmostraEndpoint,
    AmostraInfra,
    AmostraPortas,
    ContagemNginx,
    PortaEscuta,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

logger = logging.getLogger(__name__)

# Allowlist de portas base do stack — silencio total (o legado usava o mesmo
# conjunto no daemon; PORT_MAINTENANCE e tratado nas watch_rules).
PORTAS_PADRAO_PERMITIDAS: frozenset[int] = frozenset({22, 80, 443, 53, 8000, 8100})


# ---------------------------------------------------------------------------
# Protocols — "…ComoAssinatura": a superficie minima que cada collector
# precisa expor para as watch_rules; os testes injetam fakes que a satisfazem.
# ---------------------------------------------------------------------------
class InfraCollectorComoAssinatura(Protocol):
    def coletar(self) -> AmostraInfra: ...


class EndpointCollectorComoAssinatura(Protocol):
    def coletar(self, url: str) -> AmostraEndpoint: ...


class PortCollectorComoAssinatura(Protocol):
    def coletar(self) -> AmostraPortas: ...


class LogCollectorComoAssinatura(Protocol):
    def coletar_nginx(self) -> ContagemNginx: ...
    def coletar_auth(self) -> AmostraAuth: ...


class ProcessCollectorComoAssinatura(Protocol):
    def coletar(self) -> list[str]: ...


# ---------------------------------------------------------------------------
# psutil opcional (mesmo contrato do `_psutil()` legado)
# ---------------------------------------------------------------------------
def _psutil() -> Any:
    """Retorna o modulo psutil (tipado como Any — dep opcional) ou None."""
    try:
        import psutil
    except ImportError:
        logger.warning("psutil nao instalado — instale o extra: pip install 'batman-os[observe]'")
        return None
    return psutil


# ---------------------------------------------------------------------------
# Impls reais
# ---------------------------------------------------------------------------
class InfraCollectorPsutil:
    """CPU/RAM/disco via psutil. Amostra vazia se psutil indisponivel."""

    def __init__(self, mount: str = "/", cpu_interval: float = 1.0) -> None:
        self._mount = mount
        self._cpu_interval = cpu_interval

    def coletar(self) -> AmostraInfra:
        ps = _psutil()
        if ps is None:
            return AmostraInfra()
        try:
            disk = ps.disk_usage(self._mount)
            mem = ps.virtual_memory()
            return AmostraInfra(
                cpu_percent=float(ps.cpu_percent(interval=self._cpu_interval)),
                ram_percent=float(mem.percent),
                ram_available_gb=round(mem.available / 1e9, 2),
                disk_percent=float(disk.percent),
                disk_free_gb=round(disk.free / 1e9, 2),
                mount=self._mount,
            )
        except Exception as exc:  # coleta best-effort, jamais derruba o ciclo
            logger.warning("InfraCollectorPsutil falhou: %s", exc)
            return AmostraInfra(mount=self._mount)


class EndpointCollectorUrllib:
    """Probe HTTP via urllib (stdlib — sem dependencia nova).

    Detecta **down real**: timeout e conn-refused viram `ok=False` com
    `status=None` (o daemon legado vivo so olhava latencia). `sondagens`
    permite N probes para uma janela de latencia real usada no p95.
    `headers_hardening` (opcional) checa presenca de headers de seguranca.
    """

    def __init__(
        self,
        timeout: float = 8.0,
        sondagens: int = 1,
        headers_hardening: Iterable[str] | None = None,
    ) -> None:
        self._timeout = timeout
        self._sondagens = max(1, sondagens)
        self._headers_hardening = list(headers_hardening) if headers_hardening is not None else None

    def coletar(self, url: str) -> AmostraEndpoint:
        latencias: list[float] = []
        status: int | None = None
        erro: str | None = None
        ok = False
        headers_presentes: list[str] | None = None
        for _ in range(self._sondagens):
            inicio = time.monotonic()
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Batman-Observe/1.0"})
                with urllib.request.urlopen(req, timeout=self._timeout) as resp:  # noqa: S310
                    status = int(resp.status)
                    latencias.append(round((time.monotonic() - inicio) * 1000, 1))
                    ok = 200 <= status < 400
                    if self._headers_hardening is not None:
                        presentes = {k.lower() for k in resp.headers.keys()}
                        headers_presentes = [
                            h for h in self._headers_hardening if h.lower() in presentes
                        ]
            except urllib.error.HTTPError as exc:
                status = int(exc.code)
                latencias.append(round((time.monotonic() - inicio) * 1000, 1))
                erro = str(exc)
                ok = 200 <= status < 400
            except Exception as exc:  # timeout, conn-refused, DNS — down real
                latencias.append(round((time.monotonic() - inicio) * 1000, 1))
                erro = str(exc)
                ok = False
        return AmostraEndpoint(
            url=url,
            ok=ok,
            status=status,
            latency_ms=latencias[-1] if latencias else None,
            latencias_janela_ms=latencias,
            error=erro,
            headers_presentes=headers_presentes,
        )


class PortCollectorPsutil:
    """Portas TCP em LISTEN com bind real via psutil."""

    def __init__(self, permitidas: Iterable[int] | None = None) -> None:
        self._permitidas = (
            frozenset(permitidas) if permitidas is not None else PORTAS_PADRAO_PERMITIDAS
        )

    def coletar(self) -> AmostraPortas:
        ps = _psutil()
        if ps is None:
            return AmostraPortas()
        try:
            conns = ps.net_connections(kind="tcp")
        except Exception as exc:
            return AmostraPortas(erro=str(exc))
        bind_por_porta: dict[int, str] = {}
        for c in conns:
            if c.status == "LISTEN" and c.laddr:
                bind_por_porta[c.laddr.port] = c.laddr.ip
        listening = sorted(bind_por_porta)
        inesperadas = [
            PortaEscuta(port=p, bind=bind_por_porta.get(p, ""))
            for p in listening
            if p not in self._permitidas
        ]
        return AmostraPortas(listening=listening, inesperadas=inesperadas)


class ProcessCollectorPsutil:
    """Nomes (lowercase) dos processos em execucao, via psutil."""

    def coletar(self) -> list[str]:
        ps = _psutil()
        if ps is None:
            return []
        try:
            nomes = {
                p.info["name"].lower() for p in ps.process_iter(["name"]) if p.info.get("name")
            }
        except Exception:
            return []
        return sorted(nomes)


def _tail(path: str, n: int) -> list[str]:
    """Ultimas n linhas de um arquivo de log. Silencioso se inacessivel."""
    try:
        with open(path, errors="replace") as f:
            return f.readlines()[-n:]
    except OSError:
        return []


class LogCollectorTail:
    """Tail de nginx access.log + auth.log -> contagens por janela.

    Faz o parsing que o legado espalhava entre `daemon.py` e as watch_rules
    mortas, numa fonte so: 5xx/404/401-403 do nginx e falhas/sucessos SSH
    por IP (materia-prima do `auth_bypass` calculado).
    """

    _STATUS_RE = re.compile(r'"[A-Z]+ \S+ HTTP/[\d.]+" (\d{3})')
    _IP_STATUS_RE = re.compile(r'^(\d{1,3}(?:\.\d{1,3}){3}).*" (\d{3}) ')
    _SSH_FALHA_RE = re.compile(r"Failed password|Invalid user|authentication failure", re.I)
    _SSH_OK_RE = re.compile(r"Accepted (?:password|publickey)", re.I)
    _IP_RE = re.compile(r"from (\d{1,3}(?:\.\d{1,3}){3})")

    def __init__(
        self,
        nginx_log: str = "/var/log/nginx/access.log",
        auth_log: str = "/var/log/auth.log",
        janela_nginx: int = 500,
        janela_auth: int = 300,
    ) -> None:
        self._nginx_log = nginx_log
        self._auth_log = auth_log
        self._janela_nginx = janela_nginx
        self._janela_auth = janela_auth

    def coletar_nginx(self) -> ContagemNginx:
        linhas = _tail(self._nginx_log, self._janela_nginx)
        total = 0
        status_5xx = 0
        auth_401_403 = 0
        por_ip_404: Counter[str] = Counter()
        for linha in linhas:
            m = self._STATUS_RE.search(linha)
            if not m:
                continue
            total += 1
            status = int(m.group(1))
            if status >= 500:
                status_5xx += 1
            elif status in (401, 403):
                auth_401_403 += 1
            elif status == 404:
                mi = self._IP_STATUS_RE.search(linha)
                if mi:
                    por_ip_404[mi.group(1)] += 1
        return ContagemNginx(
            total=total,
            status_5xx=status_5xx,
            por_ip_404=dict(por_ip_404),
            auth_401_403=auth_401_403,
        )

    def coletar_auth(self) -> AmostraAuth:
        linhas = _tail(self._auth_log, self._janela_auth)
        falhas_por_ip: Counter[str] = Counter()
        sucessos_por_ip: Counter[str] = Counter()
        falhas = 0
        for linha in linhas:
            ip_m = self._IP_RE.search(linha)
            ip = ip_m.group(1) if ip_m else "?"
            if self._SSH_FALHA_RE.search(linha):
                falhas += 1
                falhas_por_ip[ip] += 1
            elif self._SSH_OK_RE.search(linha):
                sucessos_por_ip[ip] += 1
        ip_top = falhas_por_ip.most_common(1)[0][0] if falhas_por_ip else "?"
        return AmostraAuth(
            total_linhas=len(linhas),
            falhas=falhas,
            ip_top=ip_top,
            falhas_por_ip=dict(falhas_por_ip),
            sucessos_por_ip=dict(sucessos_por_ip),
        )
