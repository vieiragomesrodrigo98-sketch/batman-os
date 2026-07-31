"""Snapshot de observabilidade — o estado bruto coletado num ciclo.

Anexo ao Vol.VII Cap.27/30 (subsistema `batman_os.observe`). Um
`ObserveSnapshot` e a foto imutavel de tudo que os collectors mediram num
ciclo; as `watch_rules` (funcoes puras) derivam alertas dele. Carregar o
snapshot como um modelo Pydantic (e nao dicts soltos, como o legado)
torna `run_once` deterministico e trivialmente testavel sem I/O.

Multi-tenant (ADR-0005): o snapshot carrega `tenant_id`; todo alerta
derivado herda esse tenant para o sink rotear (ADR-0005).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from batman_os.foundation.types import TenantId


class AmostraInfra(BaseModel):
    """CPU/RAM/disco — o que o legado coletava via psutil em `collect_infra`."""

    cpu_percent: float | None = None
    ram_percent: float | None = None
    ram_available_gb: float | None = None
    disk_percent: float | None = None
    disk_free_gb: float | None = None
    mount: str = "/"


class AmostraEndpoint(BaseModel):
    """Probe HTTP de um endpoint.

    `ok=False` marca **down real** (timeout/conn-refused/5xx) — a melhoria
    sobre o legado, cujo daemon vivo so olhava latencia e nunca emitia
    down. `latencias_janela_ms` carrega a JANELA de amostras para o p95
    real (o legado rotulava a latencia de 1 request como "p95").
    `headers_presentes=None` significa "nao coletado" (a regra de headers
    ignora); uma lista (mesmo vazia) significa coletado.
    """

    url: str
    ok: bool
    status: int | None = None
    latency_ms: float | None = None
    latencias_janela_ms: list[float] = Field(default_factory=list)
    error: str | None = None
    headers_presentes: list[str] | None = None
    exposto: bool = False
    path: str | None = None


class PortaEscuta(BaseModel):
    """Uma porta TCP em LISTEN com bind real (nao hardcoded)."""

    port: int
    bind: str = ""
    service: str = "?"


class AmostraPortas(BaseModel):
    """Portas em escuta + as inesperadas (fora da allowlist do collector)."""

    listening: list[int] = Field(default_factory=list)
    inesperadas: list[PortaEscuta] = Field(default_factory=list)
    erro: str | None = None


class ContagemNginx(BaseModel):
    """Contagens agregadas de uma janela do access.log do nginx."""

    total: int = 0
    status_5xx: int = 0
    por_ip_404: dict[str, int] = Field(default_factory=dict)
    auth_401_403: int = 0


class AmostraAuth(BaseModel):
    """Sinais de brute-force/auth-bypass do auth.log.

    `auth_bypass` do legado era hardcoded `False`; aqui ele e CALCULADO por
    `watch_rules` a partir de `sucessos_por_ip` vs `falhas_por_ip` (login
    aceito de um IP com muitas falhas recentes = sucesso anomalo).
    """

    total_linhas: int = 0
    falhas: int = 0
    ip_top: str = "?"
    falhas_por_ip: dict[str, int] = Field(default_factory=dict)
    sucessos_por_ip: dict[str, int] = Field(default_factory=dict)


class ObserveSnapshot(BaseModel):
    """Foto de um ciclo de observacao. Fonte unica para `watch_rules`."""

    tenant_id: TenantId | None = None
    infra: AmostraInfra | None = None
    endpoints: list[AmostraEndpoint] = Field(default_factory=list)
    portas: AmostraPortas | None = None
    processos_rodando: list[str] = Field(default_factory=list)
    processos_esperados: list[str] = Field(default_factory=list)
    nginx: ContagemNginx | None = None
    auth: AmostraAuth | None = None
    nginx_config_valida: bool | None = None
    nginx_config_detalhe: str = ""
