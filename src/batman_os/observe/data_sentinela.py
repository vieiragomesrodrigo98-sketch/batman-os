"""Sentinela de saúde de DADOS em produção — capability `dados-sentinela`
(Onda 1, Plano Cobertura Total, S162). Ver `data_manifest.py` para o
contexto/motivação completos (cegueira nº2: pipeline `status=error` sem
nenhum alerta, card `PIPE_FSIM_MTM01` do radar-preditivo).

Mesmo padrão arquitetural do `FunctionalMonitor` (`functional_monitor.py`):
`run_once(manifest)` roda cada fonte declarada, monta um `GovernanceAlert`
por achado e entrega via `governance.raise_alert` (sink Discord + dedupe já
herdados). Diferença: aqui a "sonda" é o FILESYSTEM local (arquivos do
repositório alvo já deployado — `root_dir` do manifesto), não uma
requisição HTTP — dados-sentinela roda DENTRO da VPS onde os dados já
estão, não contra um endpoint.

Best-effort por fonte (mesmo espírito de `FunctionalMonitor.run_once`): uma
fonte com erro de leitura nunca derruba o ciclo inteiro.

Disciplina (contrato de paridade do subsistema `observe`): importa
`governance` + `foundation` + `observe.data_manifest` + stdlib; NUNCA
importa `batman_os.kernel` (ADR-0012).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from batman_os.foundation.types import Evidence, agora
from batman_os.governance.governance_engine import (
    FonteAlerta,
    GovernanceAlert,
    GovernanceEngine,
    SeveridadeAlerta,
)
from batman_os.observe.data_manifest import (
    DataSentinelManifest,
    FonteIdadeArquivo,
    FonteJsonlPipeline,
)

logger = logging.getLogger(__name__)

# Nº mínimo de linhas lidas do fim do arquivo antes de bucketar por janela de
# tempo — cobre a checagem de status (janela curta) E a de queda de
# contagem (janela de até 48h) sem reler o arquivo inteiro a cada ciclo de
# 5min (arquivos de log de produção acumulam dezenas de milhares de linhas).
_MAX_LINHAS_LIDAS = 5000


class DataSentinelMonitor:
    """Orquestra leitura -> avaliação -> alerta, por tenant. Sem estado
    entre ciclos (a checagem de queda de contagem é derivada dos próprios
    timestamps das linhas do log, nunca de um snapshot persistido — mais
    simples e correto sob restart do cron a cada 5min)."""

    def __init__(self, governance: GovernanceEngine) -> None:
        self._governance = governance

    def run_once(self, manifest: DataSentinelManifest) -> list[GovernanceAlert]:
        root = Path(manifest.root_dir)
        agora_ = agora()
        alertas: list[GovernanceAlert] = []

        for fonte in manifest.fontes_jsonl:
            if not fonte.habilitado:
                continue
            try:
                alertas.extend(self._checar_jsonl(root, fonte, manifest.tenant_id, agora_))
            except Exception as exc:  # best-effort: uma fonte ruim nao derruba o ciclo
                logger.error("dados-sentinela: fonte jsonl '%s' levantou: %s", fonte.id, exc)

        for fonte_idade in manifest.fontes_idade:
            if not fonte_idade.habilitado:
                continue
            try:
                alerta = self._checar_idade(root, fonte_idade, manifest.tenant_id, agora_)
                if alerta is not None:
                    alertas.append(alerta)
            except Exception as exc:
                logger.error("dados-sentinela: fonte idade '%s' levantou: %s", fonte_idade.id, exc)

        for alerta in alertas:
            self._governance.raise_alert(alerta)
        return alertas

    # -- fonte jsonl (status + contagem) ------------------------------------
    def _checar_jsonl(
        self,
        root: Path,
        fonte: FonteJsonlPipeline,
        tenant_id: Any,
        agora_: datetime,
    ) -> list[GovernanceAlert]:
        caminho = root / fonte.arquivo
        if not caminho.exists():
            return [
                GovernanceAlert(
                    source=FonteAlerta.DATA_SOURCE_MISSING,
                    severity=SeveridadeAlerta.CRITICAL,
                    evidence=[
                        Evidence(
                            origem=f"dados-sentinela:{fonte.id}",
                            evidencias=[
                                f"fonte={fonte.id} arquivo={fonte.arquivo}",
                                "arquivo ausente no disco (fonte habilitada, mas nunca escrita "
                                "ou removida)",
                            ],
                        )
                    ],
                    related_tenant_id=tenant_id,
                )
            ]

        objetos = _ler_jsonl_recente(caminho, _MAX_LINHAS_LIDAS)
        alertas: list[GovernanceAlert] = []

        erro = _achado_status_erro(fonte, objetos, tenant_id)
        if erro is not None:
            alertas.append(erro)

        queda = _achado_queda_contagem(fonte, objetos, tenant_id, agora_)
        if queda is not None:
            alertas.append(queda)

        return alertas

    # -- fonte de idade -------------------------------------------------------
    def _checar_idade(
        self, root: Path, fonte: FonteIdadeArquivo, tenant_id: Any, agora_: datetime
    ) -> GovernanceAlert | None:
        caminho = root / fonte.arquivo
        if not caminho.exists():
            return GovernanceAlert(
                source=FonteAlerta.DATA_SOURCE_MISSING,
                severity=SeveridadeAlerta.CRITICAL,
                evidence=[
                    Evidence(
                        origem=f"dados-sentinela:{fonte.id}",
                        evidencias=[
                            f"fonte={fonte.id} arquivo={fonte.arquivo}",
                            "arquivo ausente no disco (fonte habilitada, mas nunca escrita "
                            "ou removida)",
                        ],
                    )
                ],
                related_tenant_id=tenant_id,
            )

        if fonte.dias_uteis_apenas and _e_fim_de_semana_utc(agora_):
            return None

        mtime = datetime.fromtimestamp(caminho.stat().st_mtime, tz=UTC)
        idade_min = (agora_ - mtime).total_seconds() / 60.0
        if idade_min <= fonte.cadencia_max_minutos:
            return None
        return GovernanceAlert(
            source=FonteAlerta.DATA_SOURCE_STALE,
            severity=fonte.severidade,
            evidence=[
                Evidence(
                    origem=f"dados-sentinela:{fonte.id}",
                    evidencias=[
                        f"fonte={fonte.id} arquivo={fonte.arquivo}",
                        f"idade={round(idade_min)}min (cadência máxima "
                        f"{fonte.cadencia_max_minutos}min)",
                        f"mtime={mtime.isoformat()}",
                    ],
                )
            ],
            related_tenant_id=tenant_id,
        )


def _e_fim_de_semana_utc(momento: datetime) -> bool:
    return momento.weekday() >= 5  # 5=sábado, 6=domingo


# ---------------------------------------------------------------------------
# Leitura de arquivo (único ponto de IO deste módulo)
# ---------------------------------------------------------------------------
def _ler_jsonl_recente(caminho: Path, max_linhas: int) -> list[dict[str, Any]]:
    texto = caminho.read_text(encoding="utf-8", errors="replace")
    linhas = [linha for linha in texto.splitlines() if linha.strip()][-max_linhas:]
    objetos: list[dict[str, Any]] = []
    for linha in linhas:
        try:
            bruto = json.loads(linha)
        except json.JSONDecodeError:
            continue
        if isinstance(bruto, dict):
            objetos.append(bruto)
    return objetos


# ---------------------------------------------------------------------------
# Avaliação — funções puras sobre a lista de objetos já lidos
# ---------------------------------------------------------------------------
def _achado_status_erro(
    fonte: FonteJsonlPipeline, objetos: list[dict[str, Any]], tenant_id: Any
) -> GovernanceAlert | None:
    recentes = objetos[-fonte.linhas_recentes_para_status :]
    erros = [
        o
        for o in recentes
        if fonte.campo_status in o and str(o[fonte.campo_status]) != fonte.valor_ok
    ]
    if not erros:
        return None

    ultimo = erros[-1]
    passos_falhos = [
        str(nome)
        for nome, status in (ultimo.get("steps") or {}).items()
        if str(status) != fonte.valor_ok
    ]
    linhas_ev = [
        f"fonte={fonte.id} arquivo={fonte.arquivo}",
        f"{len(erros)} linha(s) com {fonte.campo_status}!='{fonte.valor_ok}' nas últimas "
        f"{len(recentes)} linha(s) lidas",
        f"{fonte.campo_timestamp}={ultimo.get(fonte.campo_timestamp)} "
        f"{fonte.campo_status}={ultimo.get(fonte.campo_status)}",
    ]
    if passos_falhos:
        linhas_ev.append(f"passo(s) com erro: {', '.join(sorted(passos_falhos))}")
    if ultimo.get("errors"):
        linhas_ev.append(f"errors={ultimo['errors']}")

    return GovernanceAlert(
        source=FonteAlerta.DATA_PIPELINE_ERROR,
        severity=fonte.severidade_erro,
        evidence=[Evidence(origem=f"dados-sentinela:{fonte.id}", evidencias=linhas_ev)],
        related_tenant_id=tenant_id,
    )


def _bucketar_por_janela(
    objetos: list[dict[str, Any]], campo_timestamp: str, agora_: datetime, largura_horas: float
) -> tuple[int, int]:
    """Conta quantos objetos têm timestamp na janela [agora-largura, agora]
    ("recente") e quantos na janela anterior [agora-2*largura,
    agora-largura) ("anterior") — sem nenhum estado persistido entre
    execuções, só os próprios timestamps já gravados em cada linha."""
    janela_recente_inicio = agora_ - timedelta(hours=largura_horas)
    janela_anterior_inicio = agora_ - timedelta(hours=2 * largura_horas)
    recente = anterior = 0
    for obj in objetos:
        bruto = obj.get(campo_timestamp)
        if not isinstance(bruto, str):
            continue
        try:
            ts = datetime.fromisoformat(bruto)
        except ValueError:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        if janela_recente_inicio <= ts <= agora_:
            recente += 1
        elif janela_anterior_inicio <= ts < janela_recente_inicio:
            anterior += 1
    return recente, anterior


def _achado_queda_contagem(
    fonte: FonteJsonlPipeline, objetos: list[dict[str, Any]], tenant_id: Any, agora_: datetime
) -> GovernanceAlert | None:
    if fonte.dias_uteis_apenas_para_queda and _e_fim_de_semana_utc(agora_):
        return None
    recente, anterior = _bucketar_por_janela(objetos, fonte.campo_timestamp, agora_, 24.0)
    if anterior < fonte.minimo_linhas_para_checar_queda:
        return None  # baseline pequena demais para uma queda percentual fazer sentido
    limiar = anterior * (1 - fonte.queda_percentual_max / 100.0)
    if recente >= limiar:
        return None

    queda_pct = round((1 - recente / anterior) * 100, 1)
    return GovernanceAlert(
        source=FonteAlerta.DATA_ROW_COUNT_DROP,
        severity=fonte.severidade_queda,
        evidence=[
            Evidence(
                origem=f"dados-sentinela:{fonte.id}:contagem",
                evidencias=[
                    f"fonte={fonte.id} arquivo={fonte.arquivo}",
                    f"contagem_linhas 24h atual={recente} vs 24h anterior={anterior} "
                    f"(queda {queda_pct}%, limiar {fonte.queda_percentual_max}%)",
                ],
            )
        ],
        related_tenant_id=tenant_id,
    )
