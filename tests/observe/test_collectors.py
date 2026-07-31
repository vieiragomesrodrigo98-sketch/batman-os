"""Testes dos collectors — 100% com fakes/Protocols, ZERO psutil/rede real.

Cobre: (1) o padrao "…ComoAssinatura" (fakes que satisfazem os Protocols),
(2) a degradacao das impls reais quando psutil falta (retorno vazio, nunca
levanta), (3) o parser real do `LogCollectorTail` sobre arquivos temporarios
(I/O de arquivo deterministico, sem psutil/rede), (4) o `EndpointCollectorUrllib`
com `urlopen` fake (down real vs ok, janela de latencia)."""

from __future__ import annotations

import urllib.error
from pathlib import Path
from typing import Any

from batman_os.observe import collectors
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
from batman_os.observe.snapshot import (
    AmostraAuth,
    AmostraEndpoint,
    AmostraInfra,
    AmostraPortas,
    ContagemNginx,
    PortaEscuta,
)


# ---------------------------------------------------------------------------
# Fakes que satisfazem os Protocols (checagem estrutural pelo mypy + runtime)
# ---------------------------------------------------------------------------
class _InfraFake:
    def coletar(self) -> AmostraInfra:
        return AmostraInfra(cpu_percent=42.0, ram_percent=30.0, disk_percent=10.0)


class _EndpointFake:
    def coletar(self, url: str) -> AmostraEndpoint:
        return AmostraEndpoint(url=url, ok=True, status=200, latency_ms=12.0)


class _PortFake:
    def coletar(self) -> AmostraPortas:
        return AmostraPortas(listening=[22, 80], inesperadas=[])


class _LogFake:
    def coletar_nginx(self) -> ContagemNginx:
        return ContagemNginx(total=10, status_5xx=0)

    def coletar_auth(self) -> AmostraAuth:
        return AmostraAuth(total_linhas=5, falhas=0)


class _ProcessFake:
    def coletar(self) -> list[str]:
        return ["bash", "nginx"]


class TestProtocolsAceitamFakes:
    def test_fakes_satisfazem_protocols(self) -> None:
        infra: InfraCollectorComoAssinatura = _InfraFake()
        endpoint: EndpointCollectorComoAssinatura = _EndpointFake()
        porta: PortCollectorComoAssinatura = _PortFake()
        log: LogCollectorComoAssinatura = _LogFake()
        proc: ProcessCollectorComoAssinatura = _ProcessFake()

        assert infra.coletar().cpu_percent == 42.0
        assert endpoint.coletar("https://x").ok is True
        assert porta.coletar().listening == [22, 80]
        assert log.coletar_nginx().total == 10
        assert log.coletar_auth().falhas == 0
        assert proc.coletar() == ["bash", "nginx"]


# ---------------------------------------------------------------------------
# Degradacao das impls reais sem psutil (psutil ausente no CI)
# ---------------------------------------------------------------------------
class TestDegradacaoSemPsutil:
    def test_infra_sem_psutil_retorna_vazio(self, monkeypatch: Any) -> None:
        monkeypatch.setattr(collectors, "_psutil", lambda: None)
        amostra = InfraCollectorPsutil().coletar()
        assert amostra.cpu_percent is None
        assert amostra.ram_percent is None

    def test_portas_sem_psutil_retorna_vazio(self, monkeypatch: Any) -> None:
        monkeypatch.setattr(collectors, "_psutil", lambda: None)
        amostra = PortCollectorPsutil().coletar()
        assert amostra.listening == []
        assert amostra.inesperadas == []

    def test_processos_sem_psutil_retorna_lista_vazia(self, monkeypatch: Any) -> None:
        monkeypatch.setattr(collectors, "_psutil", lambda: None)
        assert ProcessCollectorPsutil().coletar() == []


# ---------------------------------------------------------------------------
# psutil FAKE (stand-in, nao o modulo real) — cobre o ramo de parsing
# ---------------------------------------------------------------------------
class _FakeDisk:
    percent = 73.0
    free = 12_000_000_000


class _FakeMem:
    percent = 55.0
    available = 4_000_000_000


class _FakeAddr:
    def __init__(self, ip: str, port: int) -> None:
        self.ip = ip
        self.port = port


class _FakeConn:
    def __init__(self, status: str, ip: str, port: int) -> None:
        self.status = status
        self.laddr = _FakeAddr(ip, port)


class _FakeProc:
    def __init__(self, name: str) -> None:
        self.info = {"name": name}


class _FakePsutil:
    def disk_usage(self, mount: str) -> _FakeDisk:
        return _FakeDisk()

    def virtual_memory(self) -> _FakeMem:
        return _FakeMem()

    def cpu_percent(self, interval: float) -> float:
        return 61.0

    def net_connections(self, kind: str) -> list[_FakeConn]:
        return [
            _FakeConn("LISTEN", "0.0.0.0", 22),
            _FakeConn("LISTEN", "0.0.0.0", 6379),  # inesperada
            _FakeConn("ESTABLISHED", "1.2.3.4", 51000),  # ignorada (nao LISTEN)
        ]

    def process_iter(self, attrs: list[str]) -> list[_FakeProc]:
        return [_FakeProc("Bash"), _FakeProc("xmrig")]


class TestImplsComPsutilFake:
    def test_infra_parseia(self, monkeypatch: Any) -> None:
        monkeypatch.setattr(collectors, "_psutil", lambda: _FakePsutil())
        amostra = InfraCollectorPsutil(cpu_interval=0.0).coletar()
        assert amostra.cpu_percent == 61.0
        assert amostra.ram_percent == 55.0
        assert amostra.disk_percent == 73.0

    def test_portas_detecta_inesperada(self, monkeypatch: Any) -> None:
        monkeypatch.setattr(collectors, "_psutil", lambda: _FakePsutil())
        amostra = PortCollectorPsutil(permitidas={22, 80, 443}).coletar()
        assert amostra.listening == [22, 6379]
        assert [p.port for p in amostra.inesperadas] == [6379]
        assert amostra.inesperadas[0].bind == "0.0.0.0"

    def test_processos_lowercase(self, monkeypatch: Any) -> None:
        monkeypatch.setattr(collectors, "_psutil", lambda: _FakePsutil())
        assert ProcessCollectorPsutil().coletar() == ["bash", "xmrig"]


# ---------------------------------------------------------------------------
# LogCollectorTail — parser real sobre arquivos temporarios (sem psutil/rede)
# ---------------------------------------------------------------------------
_NGINX_LINHAS = [
    '1.2.3.4 - - [x] "GET /a HTTP/1.1" 200 10',
    '1.2.3.4 - - [x] "GET /b HTTP/1.1" 500 10',
    '9.9.9.9 - - [x] "GET /c HTTP/1.1" 404 10',
    '9.9.9.9 - - [x] "GET /d HTTP/1.1" 401 10',
    '9.9.9.9 - - [x] "GET /e HTTP/1.1" 403 10',
]
_AUTH_LINHAS = [
    "Failed password for root from 9.9.9.9 port 1",
    "Failed password for root from 9.9.9.9 port 2",
    "Invalid user admin from 9.9.9.9 port 3",
    "Accepted password for root from 9.9.9.9 port 4",
    "Accepted publickey for deploy from 5.5.5.5 port 5",
]


class TestLogCollectorTail:
    def test_nginx_conta_5xx_404_e_401_403(self, tmp_path: Path) -> None:
        log = tmp_path / "access.log"
        log.write_text("\n".join(_NGINX_LINHAS) + "\n", encoding="utf-8")
        contagem = LogCollectorTail(nginx_log=str(log)).coletar_nginx()
        assert contagem.total == 5
        assert contagem.status_5xx == 1
        assert contagem.auth_401_403 == 2
        assert contagem.por_ip_404 == {"9.9.9.9": 1}

    def test_auth_conta_falhas_e_sucessos_por_ip(self, tmp_path: Path) -> None:
        log = tmp_path / "auth.log"
        log.write_text("\n".join(_AUTH_LINHAS) + "\n", encoding="utf-8")
        amostra = LogCollectorTail(auth_log=str(log)).coletar_auth()
        assert amostra.falhas == 3
        assert amostra.falhas_por_ip == {"9.9.9.9": 3}
        assert amostra.sucessos_por_ip == {"9.9.9.9": 1, "5.5.5.5": 1}
        assert amostra.ip_top == "9.9.9.9"

    def test_arquivo_inexistente_e_silencioso(self) -> None:
        col = LogCollectorTail(nginx_log="/nao/existe.log", auth_log="/nao/existe.log")
        assert col.coletar_nginx().total == 0
        assert col.coletar_auth().falhas == 0


# ---------------------------------------------------------------------------
# EndpointCollectorUrllib — urlopen fake (down real vs ok, janela de latencia)
# ---------------------------------------------------------------------------
class _RespFake:
    def __init__(self, status: int, headers: dict[str, str] | None = None) -> None:
        self.status = status
        self.headers = headers or {}

    def __enter__(self) -> _RespFake:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


class TestEndpointCollectorUrllib:
    def test_ok_com_janela_de_latencia(self, monkeypatch: Any) -> None:
        monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _RespFake(200))
        amostra = EndpointCollectorUrllib(sondagens=3).coletar("https://x")
        assert amostra.ok is True
        assert amostra.status == 200
        assert len(amostra.latencias_janela_ms) == 3

    def test_down_real_quando_conexao_recusada(self, monkeypatch: Any) -> None:
        def _boom(*a: object, **k: object) -> None:
            raise urllib.error.URLError("connection refused")

        monkeypatch.setattr("urllib.request.urlopen", _boom)
        amostra = EndpointCollectorUrllib().coletar("https://x")
        assert amostra.ok is False
        assert amostra.status is None
        assert amostra.error is not None

    def test_5xx_nao_e_ok(self, monkeypatch: Any) -> None:
        def _http_error(*a: object, **k: object) -> None:
            raise urllib.error.HTTPError("https://x", 503, "boom", {}, None)  # type: ignore[arg-type]

        monkeypatch.setattr("urllib.request.urlopen", _http_error)
        amostra = EndpointCollectorUrllib().coletar("https://x")
        assert amostra.ok is False
        assert amostra.status == 503

    def test_headers_hardening_coletados(self, monkeypatch: Any) -> None:
        monkeypatch.setattr(
            "urllib.request.urlopen",
            lambda *a, **k: _RespFake(200, {"Strict-Transport-Security": "max-age=1"}),
        )
        amostra = EndpointCollectorUrllib(
            headers_hardening=["Strict-Transport-Security", "Content-Security-Policy"]
        ).coletar("https://x")
        assert amostra.headers_presentes == ["Strict-Transport-Security"]


# assembly minima (uso conjunto dos fakes, como um coletor de snapshot faria)
def test_assembly_com_fakes_monta_snapshot_pieces() -> None:
    infra = _InfraFake().coletar()
    porta = PortaEscuta(port=22, bind="0.0.0.0")
    assert infra.cpu_percent == 42.0
    assert porta.port == 22
