"""Monitor funcional / sintetico — exercita as funcionalidades entregues ao
usuario e alarma quando elas nao sao entregues.

Fonte da verdade: `docs/observe/MONITOR_FUNCIONAL.md`. Distinto do
`ObserveWatcher` (infra: CPU/RAM/porta): aqui a jornada do usuario e
exercitada de verdade (login sintetico -> sonda -> asercao de conteudo) e
falha mesmo com CPU baixo e HTTP 200.

Segue o MESMO padrao do `ObserveWatcher.run_once`: monta um `GovernanceAlert`
por evento e chama `governance.raise_alert` (entrega via `DiscordAlertSink`,
cujo dedupe por estado ja evita spam de um check que segue caido). Best-effort:
a falha de um check nunca derruba o ciclo dos outros. Multi-tenant (ADR-0005):
todo alerta herda o `related_tenant_id` do manifesto.

Disciplina (contrato de paridade): importa `governance` + `foundation` +
`observe.feature_manifest` + stdlib/pydantic; NUNCA importa `batman_os.kernel`
(ADR-0012).
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable, Mapping
from typing import Any, Protocol

from pydantic import BaseModel, Field

from batman_os.foundation.types import Evidence, Timestamp, agora
from batman_os.governance.governance_engine import (
    FonteAlerta,
    GovernanceAlert,
    GovernanceEngine,
    SeveridadeAlerta,
)
from batman_os.observe.feature_manifest import (
    AuthConfig,
    FeatureCheck,
    FeatureManifest,
    avaliar_conteudo,
    resolver_caminho,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Sonda HTTP — Protocol injetavel (testes usam fake, sem rede)
# ---------------------------------------------------------------------------
class RespostaSonda(BaseModel):
    """Resposta de uma sonda: status + CORPO (texto) + latencia; `down=True`
    marca down real (timeout/conn-refused, `status=None`)."""

    status: int | None
    corpo: str = ""
    latency_ms: float = 0.0
    down: bool = False
    erro: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)


class SondadorComoAssinatura(Protocol):
    """Superficie minima da sonda — espelha o `EndpointCollectorComoAssinatura`
    do watcher, mas com metodo, headers (Bearer), corpo JSON e o CORPO da
    resposta. Testes injetam um fake que a satisfaz (sem rede)."""

    def sondar(
        self,
        *,
        url: str,
        metodo: str = "GET",
        headers: Mapping[str, str] | None = None,
        corpo: Mapping[str, Any] | None = None,
        timeout_s: float = 8.0,
    ) -> RespostaSonda: ...


class SondadorUrllib:
    """Sonda real via urllib (stdlib — sem dependencia nova). Reusa o padrao de
    probe robusto do `EndpointCollectorUrllib` (timeout, down real em
    timeout/conn-refused) e adiciona metodo, headers, corpo JSON e a leitura do
    CORPO da resposta (necessarios para asserir a entrega da feature)."""

    def __init__(self, max_corpo_bytes: int = 64 * 1024) -> None:
        self._max = max_corpo_bytes

    def sondar(
        self,
        *,
        url: str,
        metodo: str = "GET",
        headers: Mapping[str, str] | None = None,
        corpo: Mapping[str, Any] | None = None,
        timeout_s: float = 8.0,
    ) -> RespostaSonda:
        cabecalhos: dict[str, str] = {"User-Agent": "Batman-FeatureMonitor/1.0"}
        dados: bytes | None = None
        if corpo is not None:
            dados = json.dumps(corpo).encode("utf-8")
            cabecalhos["Content-Type"] = "application/json"
        if headers:
            cabecalhos.update(headers)
        inicio = time.monotonic()
        req = urllib.request.Request(url, data=dados, headers=cabecalhos, method=metodo)
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:  # noqa: S310
                texto = resp.read(self._max).decode("utf-8", errors="replace")
                lat = round((time.monotonic() - inicio) * 1000, 1)
                return RespostaSonda(
                    status=int(resp.status),
                    corpo=texto,
                    latency_ms=lat,
                    headers={k: v for k, v in resp.headers.items()},
                )
        except urllib.error.HTTPError as exc:
            texto = ""
            try:
                texto = exc.read(self._max).decode("utf-8", errors="replace")
            except Exception:  # corpo do erro e opcional
                pass
            lat = round((time.monotonic() - inicio) * 1000, 1)
            cabecalhos_resp = {k: v for k, v in exc.headers.items()} if exc.headers else {}
            return RespostaSonda(
                status=int(exc.code),
                corpo=texto,
                latency_ms=lat,
                erro=str(exc),
                headers=cabecalhos_resp,
            )
        except Exception as exc:  # timeout, conn-refused, DNS — down real
            lat = round((time.monotonic() - inicio) * 1000, 1)
            return RespostaSonda(status=None, latency_ms=lat, down=True, erro=str(exc))


# ---------------------------------------------------------------------------
# Provedor de credenciais — Protocol injetavel (env por padrao, fake em teste)
# ---------------------------------------------------------------------------
class ProvedorCredenciaisComoAssinatura(Protocol):
    def obter(self, nome_var: str) -> str | None: ...


class CredenciaisDoAmbiente:
    """Le a credencial sintetica de uma variavel de ambiente (cofre/env, fora
    do repo). Nunca ha segredo hardcoded."""

    def obter(self, nome_var: str) -> str | None:
        return os.environ.get(nome_var)


class EventoDeParadaComoAssinatura(Protocol):
    def is_set(self) -> bool: ...


class DormirComoAssinatura(Protocol):
    def __call__(self, segundos: float) -> object: ...


def _url(base: str, caminho: str) -> str:
    return base.rstrip("/") + "/" + caminho.lstrip("/")


def _extrair_token(corpo: str, token_em: str) -> str | None:
    caminho = token_em if token_em.startswith(".") else f".{token_em}"
    try:
        dados = json.loads(corpo)
    except (json.JSONDecodeError, ValueError):
        return None
    for encontrado, valor in resolver_caminho(caminho, dados):
        if encontrado and isinstance(valor, str) and valor:
            return valor
    return None


# ---------------------------------------------------------------------------
# FunctionalMonitor
# ---------------------------------------------------------------------------
class FunctionalMonitor:
    """Orquestra login sintetico -> sonda -> asercao -> alerta, por tenant.

    Estado de "estava caido" e de "rota ausente ha N ciclos" e mantido em
    memoria (dict por check.id) para detectar recuperacao e drift 404/410."""

    def __init__(
        self,
        governance: GovernanceEngine,
        *,
        sondador: SondadorComoAssinatura | None = None,
        credenciais: ProvedorCredenciaisComoAssinatura | None = None,
        relogio: Callable[[], Timestamp] | None = None,
    ) -> None:
        self._governance = governance
        self._sondador: SondadorComoAssinatura = sondador or SondadorUrllib()
        self._credenciais: ProvedorCredenciaisComoAssinatura = (
            credenciais or CredenciaisDoAmbiente()
        )
        self._relogio = relogio or agora
        self._estado_caido: dict[str, bool] = {}
        self._contador_rota_ausente: dict[str, int] = {}
        # Introspeccao do ultimo ciclo: checks que nao rodaram por falta de
        # credencial (config, nao outage). Nao vira GovernanceAlert.
        self.ultimos_pulados: list[str] = []

    # -- ciclo unico --------------------------------------------------------
    def run_once(self, manifest: FeatureManifest) -> list[GovernanceAlert]:
        """Roda cada `FeatureCheck` habilitado uma vez. Best-effort: a falha de
        um check e logada e o ciclo continua. Cada alerta e entregue via
        `governance.raise_alert` (sink). Autentica no maximo uma vez por tipo
        de sessao por ciclo (respeita o rate-limit de login do seed)."""
        alertas: list[GovernanceAlert] = []
        self.ultimos_pulados = []
        tokens: dict[str, str | None] = {}
        for check in manifest.features:
            if not check.habilitado:
                continue
            try:
                alerta = self._avaliar_check(manifest, check, tokens)
            except Exception as exc:  # best-effort: um check ruim nao derruba o ciclo
                logger.error("check funcional '%s' levantou (ciclo continua): %s", check.id, exc)
                continue
            if alerta is not None:
                self._governance.raise_alert(alerta)
                alertas.append(alerta)
        return alertas

    def _avaliar_check(
        self, manifest: FeatureManifest, check: FeatureCheck, tokens: dict[str, str | None]
    ) -> GovernanceAlert | None:
        headers: dict[str, str] = {}
        if check.auth != "none":
            token = self._obter_token(manifest, check.auth, tokens)
            if token is None:
                self.ultimos_pulados.append(check.id)
                logger.warning(
                    "check '%s' pulado: credencial de %s ausente (config, nao outage)",
                    check.id,
                    check.auth,
                )
                return None
            headers["Authorization"] = f"Bearer {token}"
        credencial_ok, corpo = self._materializar_corpo(manifest, check.corpo)
        if not credencial_ok:
            self.ultimos_pulados.append(check.id)
            logger.warning(
                "check '%s' pulado: corpo exige credencial ausente (config, nao outage)",
                check.id,
            )
            return None
        resp = self._sondador.sondar(
            url=_url(manifest.base_url, check.caminho),
            metodo=check.metodo,
            headers=headers or None,
            corpo=corpo,
            timeout_s=check.timeout_s,
        )
        return self._avaliar_resposta(manifest, check, resp)

    # -- avaliacao da resposta ---------------------------------------------
    def _avaliar_resposta(
        self, manifest: FeatureManifest, check: FeatureCheck, resp: RespostaSonda
    ) -> GovernanceAlert | None:
        estava_caido = self._estado_caido.get(check.id, False)

        # Rota removida: 404/410 consistente por N ciclos => manifesto defasado
        # (MANIFEST_DRIFT), nunca outage (design sec.3).
        if resp.status in (404, 410):
            contagem = self._contador_rota_ausente.get(check.id, 0) + 1
            self._contador_rota_ausente[check.id] = contagem
            if contagem >= manifest.drift.ciclos_para_confirmar_removida:
                self._contador_rota_ausente[check.id] = 0
                return self._alerta_drift_removida(manifest, check, resp, contagem)
            return None  # ainda nao confirmado — nunca alarma outage por 404/410
        self._contador_rota_ausente[check.id] = 0

        # Status tolerado (nao-outage): carteira 403/503, chat 429.
        if resp.status is not None and resp.status in check.status_tolerados:
            return self._registrar_ok(
                manifest, check, resp, estava_caido, nota=f"status {resp.status} tolerado"
            )

        detalhes: list[str] = []
        if resp.down or resp.status is None:
            detalhes.append(f"down real: {resp.erro or 'sem resposta'}")
        elif resp.status != check.espera_status:
            detalhes.append(f"status esperado={check.espera_status} obtido={resp.status}")
        else:
            resultado = avaliar_conteudo(check.espera_conteudo, resp.corpo)
            if not resultado.ok:
                detalhes.append(f"conteudo: {resultado.detalhe}")
            elif resp.latency_ms >= check.timeout_s * 1000:
                detalhes.append(
                    f"latencia {resp.latency_ms}ms >= teto {int(check.timeout_s * 1000)}ms"
                )

        if detalhes:
            return self._alerta_down(manifest, check, resp, detalhes)
        return self._registrar_ok(manifest, check, resp, estava_caido)

    def _registrar_ok(
        self,
        manifest: FeatureManifest,
        check: FeatureCheck,
        resp: RespostaSonda,
        estava_caido: bool,
        nota: str = "",
    ) -> GovernanceAlert | None:
        self._estado_caido[check.id] = False
        if estava_caido:
            return self._alerta_recuperado(manifest, check, resp, nota)
        return None

    # -- construcao dos alertas (mesmo padrao do ObserveWatcher) -----------
    def _alerta_down(
        self,
        manifest: FeatureManifest,
        check: FeatureCheck,
        resp: RespostaSonda,
        detalhes: list[str],
    ) -> GovernanceAlert:
        self._estado_caido[check.id] = True
        linhas = [
            f"feature={check.id} ({check.descricao})",
            f"{check.metodo} {check.caminho}",
            *detalhes,
            f"latencia={resp.latency_ms}ms",
        ]
        trecho = resp.corpo.strip().replace("\n", " ")[:200]
        if trecho:
            linhas.append(f"corpo[:200]={trecho}")
        return GovernanceAlert(
            source=FonteAlerta.FEATURE_DOWN,
            severity=check.severidade_se_cair,
            evidence=[Evidence(origem=f"feature-monitor:{check.id}", evidencias=linhas)],
            related_tenant_id=manifest.tenant_id,
        )

    def _alerta_recuperado(
        self, manifest: FeatureManifest, check: FeatureCheck, resp: RespostaSonda, nota: str
    ) -> GovernanceAlert:
        linhas = [
            f"feature={check.id} ({check.descricao})",
            f"{check.metodo} {check.caminho}",
            f"status={resp.status}",
            f"latencia={resp.latency_ms}ms",
            "recuperado: check voltou a passar apos ter falhado",
        ]
        if nota:
            linhas.append(nota)
        return GovernanceAlert(
            source=FonteAlerta.FEATURE_RECOVERED,
            severity=SeveridadeAlerta.INFO,
            evidence=[Evidence(origem=f"feature-monitor:{check.id}", evidencias=linhas)],
            related_tenant_id=manifest.tenant_id,
        )

    def _alerta_drift_removida(
        self, manifest: FeatureManifest, check: FeatureCheck, resp: RespostaSonda, contagem: int
    ) -> GovernanceAlert:
        linhas = [
            f"feature={check.id} caminho={check.caminho}",
            f"status={resp.status} consistente por {contagem} ciclo(s)",
            "rota provavelmente removida — manifesto defasado (nao outage). Revisar cobertura.",
        ]
        return GovernanceAlert(
            source=FonteAlerta.MANIFEST_DRIFT,
            severity=SeveridadeAlerta.WARNING,
            evidence=[Evidence(origem=f"feature-monitor:{check.id}", evidencias=linhas)],
            related_tenant_id=manifest.tenant_id,
        )

    # -- auth / corpo -------------------------------------------------------
    def _obter_token(
        self, manifest: FeatureManifest, auth_kind: str, cache: dict[str, str | None]
    ) -> str | None:
        if auth_kind in cache:
            return cache[auth_kind]
        creds = self._credenciais_login(manifest.auth, auth_kind)
        if creds is None:
            cache[auth_kind] = None
            return None
        identificador, senha = creds
        corpo = {manifest.auth.campo_credencial: identificador, manifest.auth.campo_senha: senha}
        resp = self._sondador.sondar(
            url=_url(manifest.base_url, manifest.auth.endpoint),
            metodo="POST",
            corpo=corpo,
            timeout_s=manifest.auth.timeout_s,
        )
        token = _extrair_token(resp.corpo, manifest.auth.token_em) if resp.status == 200 else None
        cache[auth_kind] = token
        return token

    def _credenciais_login(self, auth: AuthConfig, auth_kind: str) -> tuple[str, str] | None:
        if auth_kind == "sessao-prime":
            if auth.env_credencial_prime is None or auth.env_senha_prime is None:
                return None
            var_id, var_pw = auth.env_credencial_prime, auth.env_senha_prime
        else:
            var_id, var_pw = auth.env_credencial, auth.env_senha
        identificador = self._credenciais.obter(var_id)
        senha = self._credenciais.obter(var_pw)
        if not identificador or not senha:
            return None
        return identificador, senha

    def _materializar_corpo(
        self, manifest: FeatureManifest, corpo: dict[str, Any] | None
    ) -> tuple[bool, dict[str, Any] | None]:
        """Substitui os placeholders do corpo (`<uuid4>`, `<cpf>`, `<senha>`).
        Retorna `(credencial_ok, corpo)`: `credencial_ok=False` significa que o
        corpo exige uma credencial ausente — o check nao roda (config, nao
        outage)."""
        if corpo is None:
            return True, None
        creds = self._credenciais_login(manifest.auth, "sessao")
        saida: dict[str, Any] = {}
        for chave, valor in corpo.items():
            if valor == "<uuid4>":
                saida[chave] = str(uuid.uuid4())
            elif valor in ("<cpf>", "<senha>"):
                if creds is None:
                    return False, None
                saida[chave] = creds[0] if valor == "<cpf>" else creds[1]
            else:
                saida[chave] = valor
        return True, saida

    # -- salvaguarda de drift (cross-check com rotas reais) ----------------
    def checar_drift(
        self, manifest: FeatureManifest, rotas_reais: list[str]
    ) -> list[GovernanceAlert]:
        """Cross-check entre o manifesto e as rotas reais do site.

        `rotas_reais` e INJETADO (lista de paths). A fonte canonica e
        `api.main:app.routes` (rodar em staging/local — o `/openapi.json` do
        radar esta DESLIGADO em prod, ver o seed). Emite um unico
        `MANIFEST_DRIFT` (WARNING) agregando: (a) feature do manifesto cuja
        rota sumiu das rotas reais (removida); (b) rota de usuario real ausente
        do manifesto (sem cobertura), exceto as `rotas_ignoradas` (admin/metrics)."""
        rotas = set(rotas_reais)
        caminhos = {c.caminho for c in manifest.features}
        removidas = [c for c in manifest.features if c.caminho not in rotas]
        ignorar = [re.compile(p) for p in manifest.drift.rotas_ignoradas]
        novas = sorted(
            {
                r
                for r in rotas_reais
                if r not in caminhos and not any(rx.search(r) for rx in ignorar)
            }
        )
        if not removidas and not novas:
            return []
        evidencias: list[Evidence] = []
        if removidas:
            evidencias.append(
                Evidence(
                    origem="feature-monitor:drift-removidas",
                    evidencias=[
                        f"feature '{c.id}' caminho '{c.caminho}' ausente das rotas reais "
                        "(removida?)"
                        for c in removidas
                    ],
                )
            )
        if novas:
            evidencias.append(
                Evidence(
                    origem="feature-monitor:drift-sem-cobertura",
                    evidencias=[
                        f"rota '{r}' presente no site sem cobertura de monitor" for r in novas
                    ],
                )
            )
        alerta = GovernanceAlert(
            source=FonteAlerta.MANIFEST_DRIFT,
            severity=SeveridadeAlerta.WARNING,
            evidence=evidencias,
            related_tenant_id=manifest.tenant_id,
        )
        self._governance.raise_alert(alerta)
        return [alerta]

    # -- loop 5min ----------------------------------------------------------
    def run_forever(
        self,
        manifest: FeatureManifest,
        intervalo: float = 300.0,
        *,
        max_ciclos: int | None = None,
        parar: EventoDeParadaComoAssinatura | None = None,
        dormir: DormirComoAssinatura | None = None,
    ) -> int:
        """Loop de cadencia (default 5min = requisito). `run_once` por tick.
        Best-effort: excecao num ciclo e logada e o loop continua. Termina por
        `max_ciclos` ou `parar.is_set()` (para nao rodar infinito em teste)."""
        dormir_fn: DormirComoAssinatura = dormir if dormir is not None else _dormir_padrao
        ciclo = 0
        while (max_ciclos is None or ciclo < max_ciclos) and not (
            parar is not None and parar.is_set()
        ):
            ciclo += 1
            try:
                self.run_once(manifest)
            except Exception as exc:  # best-effort: ciclo ruim nao derruba o loop
                logger.error("ciclo funcional %d falhou (loop continua): %s", ciclo, exc)
            if (max_ciclos is None or ciclo < max_ciclos) and not (
                parar is not None and parar.is_set()
            ):
                dormir_fn(intervalo)
        return ciclo


def _dormir_padrao(segundos: float) -> None:
    time.sleep(segundos)
