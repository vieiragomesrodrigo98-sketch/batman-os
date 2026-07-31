"""Watch rules — a FONTE UNICA e canonica das regras de observacao.

Anexo ao Vol.VII Cap.27/30 (subsistema `batman_os.observe`). Corrige o
BATBL-007 do legado: la existiam DUAS pilhas divergentes (`dispatcher.py`
viva + `watch_rules/*.py` morta, com thresholds diferentes). Aqui ha UM
lugar so; a divergencia morre.

Duas familias de regra:

- **Regras de metrica-limiar** (CPU/RAM/disco/latencia/error-rate): se
  encaixam em metric+threshold+window e sao AVALIADAS pelo
  `ObservabilityEngine` (Cap.30). Esta modulo apenas declara os limiares
  canonicos (um lugar so) e roteia as leituras para as `TimeSeries`; o
  disparo e do engine. O `ObserveWatcher` faz a ponte.
- **Regras de evento** (endpoint-down, porta nova, processo suspeito,
  processo ausente/servico caido, nginx invalido, headers ausentes,
  endpoint exposto, SSH brute-force, brute-force 404, nao-autorizado):
  funcoes PURAS `snapshot -> list[GovernanceAlert]`. Deterministicas e
  testaveis sem I/O.

Severidade: o legado usava LOW/MEDIUM/HIGH/CRITICAL; o Batman OS usa
INFO/WARNING/CRITICAL. O mapeamento (LOW->INFO, MEDIUM/HIGH->WARNING,
CRITICAL->CRITICAL) e aplicado, MAS a severidade granular original e
PRESERVADA numa linha de `Evidence.evidencias` (`severidade_origem: HIGH`)
para nao regredir informacao (o contrato proibe regressao).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum

from batman_os.foundation.types import Evidence, TenantId, Timestamp
from batman_os.governance.governance_engine import (
    FonteAlerta,
    GovernanceAlert,
    SeveridadeAlerta,
)
from batman_os.governance.observability_engine import (
    AlertRule,
    AlertRuleId,
    MetricId,
    ModeloDeAlerta,
    PontoDeSerie,
    TimeSeries,
)
from batman_os.observe.snapshot import AmostraAuth, ObserveSnapshot

# ---------------------------------------------------------------------------
# Severidade: legado (granular) -> Batman OS
# ---------------------------------------------------------------------------


class SeveridadeOrigem(StrEnum):
    """Escala granular do Batman legado, preservada como rastro em evidencia."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


_MAPA_SEVERIDADE: dict[SeveridadeOrigem, SeveridadeAlerta] = {
    SeveridadeOrigem.LOW: SeveridadeAlerta.INFO,
    SeveridadeOrigem.MEDIUM: SeveridadeAlerta.WARNING,
    SeveridadeOrigem.HIGH: SeveridadeAlerta.WARNING,
    SeveridadeOrigem.CRITICAL: SeveridadeAlerta.CRITICAL,
}


def mapear_severidade(origem: SeveridadeOrigem) -> SeveridadeAlerta:
    """LOW->INFO, MEDIUM/HIGH->WARNING, CRITICAL->CRITICAL."""
    return _MAPA_SEVERIDADE[origem]


def _evento(
    *,
    fonte: FonteAlerta,
    severidade: SeveridadeAlerta,
    origem_sev: SeveridadeOrigem,
    origem: str,
    linhas: list[str],
    tenant: TenantId | None,
    confianca: float | None = None,
) -> GovernanceAlert:
    """Constroi um `GovernanceAlert` de regra de evento, sempre gravando a
    `severidade_origem` para nao perder a granularidade legada."""
    return GovernanceAlert(
        source=fonte,
        severity=severidade,
        evidence=[
            Evidence(
                origem=origem,
                evidencias=[*linhas, f"severidade_origem: {origem_sev.value}"],
                confianca=confianca,
            )
        ],
        related_tenant_id=tenant,
    )


# ---------------------------------------------------------------------------
# Regras de metrica-limiar (avaliadas pelo ObservabilityEngine)
# ---------------------------------------------------------------------------

JANELA_METRICA = timedelta(minutes=5)


@dataclass(frozen=True)
class LimiarBanda:
    """Limiares canonicos de uma metrica em duas bandas. Fonte UNICA do
    numero (regra AlertRule e roteamento de serie derivam daqui)."""

    warning: float
    critical: float
    fonte: FonteAlerta


# Threshold canonico = o melhor das duas pilhas do legado (contrato de
# paridade). CPU/RAM/disco: >=80 WARNING / >=90 CRITICAL. Latencia p95:
# >=500ms WARN / >=1000ms CRIT. Error-rate 5xx: >=2% WARN / >=5% CRIT.
LIMIAR_CPU = LimiarBanda(80.0, 90.0, FonteAlerta.INFRA_SATURATION)
LIMIAR_RAM = LimiarBanda(80.0, 90.0, FonteAlerta.INFRA_SATURATION)
LIMIAR_DISK = LimiarBanda(80.0, 90.0, FonteAlerta.INFRA_SATURATION)
LIMIAR_LATENCIA = LimiarBanda(500.0, 1000.0, FonteAlerta.ENDPOINT_LATENCY)
LIMIAR_ERROR_RATE = LimiarBanda(2.0, 5.0, FonteAlerta.ENDPOINT_ERROR_RATE)

METRIC_CPU = "observe.cpu"
METRIC_RAM = "observe.ram"
METRIC_DISK = "observe.disk"


def _id_warn(base: str) -> str:
    return f"{base}:warn"


def _id_crit(base: str) -> str:
    return f"{base}:crit"


def alert_rules_da_banda(base: str, banda: LimiarBanda, tenant: TenantId | None) -> list[AlertRule]:
    """Duas `AlertRule` (`above`) por metrica — uma por banda. O threshold
    vive so aqui (derivado de `LimiarBanda`), nunca duplicado."""
    return [
        AlertRule(
            id=AlertRuleId(_id_warn(base)),
            metric_id=MetricId(_id_warn(base)),
            condition="above",
            threshold=banda.warning,
            window=JANELA_METRICA,
            raises_alert_with=ModeloDeAlerta(
                source=banda.fonte,
                severity=SeveridadeAlerta.WARNING,
                related_tenant_id=tenant,
            ),
        ),
        AlertRule(
            id=AlertRuleId(_id_crit(base)),
            metric_id=MetricId(_id_crit(base)),
            condition="above",
            threshold=banda.critical,
            window=JANELA_METRICA,
            raises_alert_with=ModeloDeAlerta(
                source=banda.fonte,
                severity=SeveridadeAlerta.CRITICAL,
                related_tenant_id=tenant,
            ),
        ),
    ]


def _acima_do_piso(valor: float, piso: float) -> float:
    """O engine usa `>` estrito; o contrato pede `>=`. Empurra o valor
    exatamente no piso um epsilon acima para que a banda dispare de forma
    inclusiva (`>=`) sem alterar o `ObservabilityEngine`."""
    return valor if valor > piso else piso + 1e-9


def series_da_banda(
    base: str, banda: LimiarBanda, valor: float | None, agora_: Timestamp
) -> list[TimeSeries]:
    """Roteia a leitura para a serie da banda VENCEDORA (a de maior
    severidade cruzada), deixando a outra vazia — garante EXATAMENTE um
    alerta por metrica por ciclo (sem WARNING redundante junto do
    CRITICAL). Series sao substituidas por ciclo (deterministico)."""
    warn_pts: list[PontoDeSerie] = []
    crit_pts: list[PontoDeSerie] = []
    if valor is not None:
        if valor >= banda.critical:
            crit_pts = [PontoDeSerie(timestamp=agora_, value=_acima_do_piso(valor, banda.critical))]
        elif valor >= banda.warning:
            warn_pts = [PontoDeSerie(timestamp=agora_, value=_acima_do_piso(valor, banda.warning))]
    return [
        TimeSeries(
            metric_id=MetricId(_id_warn(base)), points=warn_pts, janela_agregacao=JANELA_METRICA
        ),
        TimeSeries(
            metric_id=MetricId(_id_crit(base)), points=crit_pts, janela_agregacao=JANELA_METRICA
        ),
    ]


def series_vazias(base: str) -> list[TimeSeries]:
    """Series zeradas de uma metrica — usadas para limpar pontos obsoletos
    de ciclos anteriores antes de realimentar (mantem `run_once` sem
    estado residual)."""
    return [
        TimeSeries(metric_id=MetricId(_id_warn(base)), points=[], janela_agregacao=JANELA_METRICA),
        TimeSeries(metric_id=MetricId(_id_crit(base)), points=[], janela_agregacao=JANELA_METRICA),
    ]


def percentil_95(valores: list[float]) -> float | None:
    """p95 real (nearest-rank) sobre a JANELA de amostras — o legado
    rotulava a latencia de 1 request como 'p95'; aqui e a janela toda."""
    if not valores:
        return None
    ordenados = sorted(valores)
    k = max(1, math.ceil(0.95 * len(ordenados)))
    return ordenados[k - 1]


def leituras_de_metrica(
    snapshot: ObserveSnapshot,
) -> list[tuple[str, LimiarBanda, float | None]]:
    """Extrai do snapshot as leituras que alimentam o ObservabilityEngine.

    Endpoints DOWN (`ok=False`) nao geram leitura de latencia — o
    `regra_endpoint_down` (CRITICAL) ja cobre; assim evita-se um alerta de
    latencia redundante no mesmo endpoint caido. Error-rate vem da JANELA
    do nginx (5xx sustentado)."""
    leituras: list[tuple[str, LimiarBanda, float | None]] = []
    infra = snapshot.infra
    if infra is not None:
        leituras.append((METRIC_CPU, LIMIAR_CPU, infra.cpu_percent))
        leituras.append((METRIC_RAM, LIMIAR_RAM, infra.ram_percent))
        leituras.append((METRIC_DISK, LIMIAR_DISK, infra.disk_percent))
    for ep in snapshot.endpoints:
        if not ep.ok:
            continue
        amostras = list(ep.latencias_janela_ms)
        if not amostras and ep.latency_ms is not None:
            amostras = [ep.latency_ms]
        leituras.append((f"observe.latency:{ep.url}", LIMIAR_LATENCIA, percentil_95(amostras)))
    nginx = snapshot.nginx
    if nginx is not None and nginx.total > 0:
        taxa = nginx.status_5xx / nginx.total * 100.0
        leituras.append(("observe.error_rate:nginx", LIMIAR_ERROR_RATE, taxa))
    return leituras


# ---------------------------------------------------------------------------
# Regras de evento — constantes canonicas
# ---------------------------------------------------------------------------

# Portas base do stack (silencio total) — allowlist do collector.
PORTAS_MANUTENCAO: dict[int, str] = {
    65529: "monarx-agent (Hostinger)",
    5679: "n8n task-runner (loopback interno)",
    8080: "backlog-automation webhook (loopback interno)",
    5678: "n8n webhook (loopback interno, proxy via nginx)",
}
_PREFIXOS_LOOPBACK = ("127.", "::1")
SERVICOS_PERIGOSOS = frozenset(
    {"redis", "postgres", "postgresql", "mysql", "mariadb", "mongo", "mongodb", "ssh", "memcached"}
)
HEADERS_HARDENING = frozenset(
    {"Strict-Transport-Security", "Content-Security-Policy", "X-Frame-Options"}
)
PROCESSOS_SUSPEITOS = frozenset(
    {
        "nmap",
        "masscan",
        "sqlmap",
        "hydra",
        "john",
        "hashcat",
        "xmrig",
        "minerd",
        "cryptominer",
        "cpuminer",
        "msfconsole",
        "msfvenom",
        "metasploit",
        "ncat",
        "socat",
    }
)
SSH_FALHAS_WARNING = 10
SSH_FALHAS_CRITICAL = 20
BRUTEFORCE_404_LIMIAR = 30
NAO_AUTORIZADO_MIN_REQ = 20
NAO_AUTORIZADO_TAXA = 0.15


# ---------------------------------------------------------------------------
# Regras de evento — funcoes puras
# ---------------------------------------------------------------------------


def regra_endpoint_down(snapshot: ObserveSnapshot) -> list[GovernanceAlert]:
    """Endpoint down (`ok=False`) -> CRITICAL. ✗→✓: so existia na pilha
    morta; o daemon vivo nunca emitia. Detecta DOWN REAL (timeout/
    conn-refused, `status=None`), nao so 5xx."""
    alertas: list[GovernanceAlert] = []
    for ep in snapshot.endpoints:
        if ep.ok:
            continue
        detalhe = f"HTTP {ep.status}" if ep.status is not None else (ep.error or "sem resposta")
        alertas.append(
            _evento(
                fonte=FonteAlerta.ENDPOINT_DOWN,
                severidade=SeveridadeAlerta.CRITICAL,
                origem_sev=SeveridadeOrigem.CRITICAL,
                origem="observe:endpoint-down",
                linhas=[
                    f"url={ep.url}",
                    f"status={ep.status if ep.status is not None else 'timeout'}",
                    f"detalhe={detalhe}",
                ],
                tenant=snapshot.tenant_id,
            )
        )
    return alertas


def regra_endpoint_exposto(snapshot: ObserveSnapshot) -> list[GovernanceAlert]:
    """Endpoint sensivel acessivel sem auth (`exposto=True`). ✗→✓: regra do
    dispatcher que nunca era emitida."""
    alertas: list[GovernanceAlert] = []
    for ep in snapshot.endpoints:
        if not ep.exposto:
            continue
        alertas.append(
            _evento(
                fonte=FonteAlerta.SECURITY_INTRUSION,
                severidade=mapear_severidade(SeveridadeOrigem.HIGH),
                origem_sev=SeveridadeOrigem.HIGH,
                origem="observe:endpoint-exposto",
                linhas=[
                    f"url={ep.url}",
                    f"path={ep.path or ep.url}",
                    f"status={ep.status}",
                ],
                tenant=snapshot.tenant_id,
            )
        )
    return alertas


def regra_porta(snapshot: ObserveSnapshot) -> list[GovernanceAlert]:
    """Porta inesperada: loopback -> WARNING; externa -> CRITICAL. Porta de
    manutencao conhecida -> INFO (LOW). Enriquece com nome do servico e
    marca servico perigoso (Redis/DB/SSH) para o `@everyone` do sink."""
    portas = snapshot.portas
    if portas is None or portas.erro:
        return []
    alertas: list[GovernanceAlert] = []
    for p in portas.inesperadas:
        if p.port in PORTAS_MANUTENCAO:
            alertas.append(
                _evento(
                    fonte=FonteAlerta.SECURITY_INTRUSION,
                    severidade=mapear_severidade(SeveridadeOrigem.LOW),
                    origem_sev=SeveridadeOrigem.LOW,
                    origem="observe:porta-manutencao",
                    linhas=[
                        f"porta={p.port}",
                        f"servico={PORTAS_MANUTENCAO[p.port]}",
                        f"bind={p.bind or 'loopback'}",
                        "esperado: infraestrutura/manutencao, sem acao",
                    ],
                    tenant=snapshot.tenant_id,
                )
            )
            continue
        loopback = (
            not p.bind
            or p.bind == "localhost"
            or any(p.bind.startswith(pref) for pref in _PREFIXOS_LOOPBACK)
        )
        origem_sev = SeveridadeOrigem.MEDIUM if loopback else SeveridadeOrigem.CRITICAL
        linhas = [
            f"porta={p.port}",
            f"servico={p.service}",
            f"bind={p.bind or '?'}",
            f"externa={'nao' if loopback else 'sim'}",
        ]
        if not loopback and p.service.lower() in SERVICOS_PERIGOSOS:
            linhas.append("servico_perigoso: redis/db/ssh exposto — merece @everyone")
        alertas.append(
            _evento(
                fonte=FonteAlerta.SECURITY_INTRUSION,
                severidade=mapear_severidade(origem_sev),
                origem_sev=origem_sev,
                origem="observe:porta-inesperada",
                linhas=linhas,
                tenant=snapshot.tenant_id,
            )
        )
    return alertas


def regra_processo_suspeito(snapshot: ObserveSnapshot) -> list[GovernanceAlert]:
    """Processo de ataque/mineracao (nmap/xmrig/sqlmap/metasploit/...) ->
    CRITICAL. ✗→✓: so existia na pilha morta."""
    rodando = {p.lower() for p in snapshot.processos_rodando}
    achados = sorted(rodando & PROCESSOS_SUSPEITOS)
    if not achados:
        return []
    return [
        _evento(
            fonte=FonteAlerta.SECURITY_INTRUSION,
            severidade=SeveridadeAlerta.CRITICAL,
            origem_sev=SeveridadeOrigem.CRITICAL,
            origem="observe:processo-suspeito",
            linhas=[f"processos={', '.join(achados)}", "acao imediata requerida"],
            tenant=snapshot.tenant_id,
        )
    ]


def regra_processo_ausente(snapshot: ObserveSnapshot) -> list[GovernanceAlert]:
    """Servico caido: processo esperado ausente -> CRITICAL. ✗→✓: a regra
    existia no dispatcher (`process_down`) mas nunca era emitida (o daemon
    vivo nao coletava a lista de esperados)."""
    rodando = {p.lower() for p in snapshot.processos_rodando}
    alertas: list[GovernanceAlert] = []
    for esperado in snapshot.processos_esperados:
        if esperado.lower() in rodando:
            continue
        alertas.append(
            _evento(
                fonte=FonteAlerta.SERVICE_DOWN,
                severidade=SeveridadeAlerta.CRITICAL,
                origem_sev=SeveridadeOrigem.HIGH,
                origem="observe:servico-caido",
                linhas=[
                    f"processo={esperado}",
                    "processo esperado ausente — nao respondeu ao health check",
                ],
                tenant=snapshot.tenant_id,
            )
        )
    return alertas


def regra_nginx_config(snapshot: ObserveSnapshot) -> list[GovernanceAlert]:
    """Config nginx invalida -> CRITICAL. ✗→✓: regra do dispatcher
    (`nginx_change`) nunca emitida. Mudanca valida reportada -> WARNING.
    `None` = nao verificado (silencio)."""
    valida = snapshot.nginx_config_valida
    if valida is None:
        return []
    if not valida:
        return [
            _evento(
                fonte=FonteAlerta.SECURITY_INTRUSION,
                severidade=SeveridadeAlerta.CRITICAL,
                origem_sev=SeveridadeOrigem.CRITICAL,
                origem="observe:nginx-invalida",
                linhas=[
                    f"detalhe={snapshot.nginx_config_detalhe or 'config nginx invalida'}",
                    "valida=nao",
                ],
                tenant=snapshot.tenant_id,
            )
        ]
    if not snapshot.nginx_config_detalhe:
        return []
    return [
        _evento(
            fonte=FonteAlerta.SECURITY_INTRUSION,
            severidade=mapear_severidade(SeveridadeOrigem.MEDIUM),
            origem_sev=SeveridadeOrigem.MEDIUM,
            origem="observe:nginx-mudanca",
            linhas=[f"detalhe={snapshot.nginx_config_detalhe}", "valida=sim"],
            tenant=snapshot.tenant_id,
        )
    ]


def regra_headers_ausentes(snapshot: ObserveSnapshot) -> list[GovernanceAlert]:
    """Headers de hardening ausentes (HSTS/CSP/X-Frame-Options) -> WARNING.
    ✗→✓: regra do dispatcher (`headers_missing`) nunca emitida. So avalia
    endpoints cujos headers foram coletados (`headers_presentes` nao None)."""
    alertas: list[GovernanceAlert] = []
    for ep in snapshot.endpoints:
        if ep.headers_presentes is None:
            continue
        faltando = sorted(HEADERS_HARDENING - set(ep.headers_presentes))
        if not faltando:
            continue
        alertas.append(
            _evento(
                fonte=FonteAlerta.SECURITY_INTRUSION,
                severidade=mapear_severidade(SeveridadeOrigem.MEDIUM),
                origem_sev=SeveridadeOrigem.MEDIUM,
                origem="observe:headers-ausentes",
                linhas=[f"url={ep.url}", f"faltando={', '.join(faltando)}"],
                tenant=snapshot.tenant_id,
            )
        )
    return alertas


def _ip_auth_bypass(auth: AmostraAuth) -> str | None:
    """`auth_bypass` CALCULADO (o legado hardcodava False): login aceito de
    um IP que tambem acumulou >= WARNING falhas na janela = sucesso anomalo
    apos brute-force."""
    for ip, sucessos in auth.sucessos_por_ip.items():
        if sucessos >= 1 and auth.falhas_por_ip.get(ip, 0) >= SSH_FALHAS_WARNING:
            return ip
    return None


def regra_ssh_bruteforce(snapshot: ObserveSnapshot) -> list[GovernanceAlert]:
    """SSH brute-force: >=10 WARNING / >=20 CRITICAL. `auth_bypass` de fato
    calculado -> CRITICAL (sucesso anomalo apos falhas)."""
    auth = snapshot.auth
    if auth is None:
        return []
    ip_bypass = _ip_auth_bypass(auth)
    if ip_bypass is not None:
        return [
            _evento(
                fonte=FonteAlerta.SECURITY_INTRUSION,
                severidade=SeveridadeAlerta.CRITICAL,
                origem_sev=SeveridadeOrigem.CRITICAL,
                origem="observe:ssh-auth-bypass",
                linhas=[
                    f"ip={ip_bypass}",
                    f"falhas={auth.falhas_por_ip.get(ip_bypass, 0)}",
                    f"sucessos={auth.sucessos_por_ip.get(ip_bypass, 0)}",
                    "sucesso anomalo apos falhas — auth_bypass=sim",
                ],
                tenant=snapshot.tenant_id,
            )
        ]
    if auth.falhas >= SSH_FALHAS_CRITICAL:
        origem_sev = SeveridadeOrigem.CRITICAL
    elif auth.falhas >= SSH_FALHAS_WARNING:
        origem_sev = SeveridadeOrigem.HIGH
    else:
        return []
    return [
        _evento(
            fonte=FonteAlerta.SECURITY_INTRUSION,
            severidade=mapear_severidade(origem_sev),
            origem_sev=origem_sev,
            origem="observe:ssh-bruteforce",
            linhas=[
                f"ip={auth.ip_top}",
                f"falhas={auth.falhas}",
                f"janela={auth.total_linhas}",
                "auth_bypass=nao",
            ],
            tenant=snapshot.tenant_id,
        )
    ]


def regra_bruteforce_404(snapshot: ObserveSnapshot) -> list[GovernanceAlert]:
    """IP com >=30 respostas 404 na janela do nginx -> WARNING (scanner)."""
    nginx = snapshot.nginx
    if nginx is None:
        return []
    alertas: list[GovernanceAlert] = []
    for ip, contagem in sorted(nginx.por_ip_404.items()):
        if contagem < BRUTEFORCE_404_LIMIAR:
            continue
        alertas.append(
            _evento(
                fonte=FonteAlerta.SECURITY_INTRUSION,
                severidade=mapear_severidade(SeveridadeOrigem.MEDIUM),
                origem_sev=SeveridadeOrigem.MEDIUM,
                origem="observe:bruteforce-404",
                linhas=[
                    f"ip={ip}",
                    f"contagem_404={contagem}",
                    f"limiar={BRUTEFORCE_404_LIMIAR}",
                ],
                tenant=snapshot.tenant_id,
            )
        )
    return alertas


def regra_nao_autorizado(snapshot: ObserveSnapshot) -> list[GovernanceAlert]:
    """Taxa de 401/403 >=15% em >=20 requests -> WARNING (credential
    stuffing / token expirado em massa)."""
    nginx = snapshot.nginx
    if nginx is None or nginx.total < NAO_AUTORIZADO_MIN_REQ:
        return []
    taxa = nginx.auth_401_403 / nginx.total
    if taxa < NAO_AUTORIZADO_TAXA:
        return []
    return [
        _evento(
            fonte=FonteAlerta.SECURITY_INTRUSION,
            severidade=mapear_severidade(SeveridadeOrigem.MEDIUM),
            origem_sev=SeveridadeOrigem.MEDIUM,
            origem="observe:nao-autorizado",
            linhas=[
                f"taxa_401_403={taxa:.1%}",
                f"contagem={nginx.auth_401_403}",
                f"total={nginx.total}",
            ],
            tenant=snapshot.tenant_id,
        )
    ]


# Ordem canonica das regras de evento (o `ObserveWatcher` percorre esta
# lista). Regras de metrica-limiar NAO entram aqui — sao do ObservabilityEngine.
REGRAS_DE_EVENTO = [
    regra_endpoint_down,
    regra_endpoint_exposto,
    regra_porta,
    regra_processo_suspeito,
    regra_processo_ausente,
    regra_nginx_config,
    regra_headers_ausentes,
    regra_ssh_bruteforce,
    regra_bruteforce_404,
    regra_nao_autorizado,
]


def avaliar_eventos(snapshot: ObserveSnapshot) -> list[GovernanceAlert]:
    """Roda todas as regras de EVENTO sobre o snapshot (funcao pura — nao
    entrega nada; quem entrega e o `ObserveWatcher` via `raise_alert`)."""
    alertas: list[GovernanceAlert] = []
    for regra in REGRAS_DE_EVENTO:
        alertas.extend(regra(snapshot))
    return alertas
