"""Manifesto declarativo de fontes de DADOS — capability `dados-sentinela`
(Onda 1, Plano Cobertura Total, `docs/PLANO_COBERTURA_TOTAL.md`, S162).

Cegueira que motivou esta construção (cegueira nº2 do plano, card
`PIPE_FSIM_MTM01` do radar-preditivo): o pipeline diário do radar terminou
com `status=error` (passo `fsim_mark_to_market`) e o monitor Batman OS deu
**0 alertas** — o monitor de então (`observe/functional_monitor.py`) só
sonda ENDPOINTS HTTP (login sintético → asserção de conteúdo), nunca leu
`update_log.jsonl` nem a idade/contagem dos arquivos de dados em produção.

Mesmo espírito arquitetural de `feature_manifest.py` (o par HTTP deste
subsistema): um manifesto TIPADO, versionado, por tenant, com uma fonte de
verdade documentada — aqui a fonte de verdade é o `infra/crontab.prod` do
repositório alvo (cadência DECLARADA por fonte, nunca inventada). Duas
formas de checagem, cada uma cobrindo uma das 3 provas da cegueira:

- `FonteJsonlPipeline` — lê um log JSONL append-only (`update_log.jsonl`):
  (a) linha com `status != "ok"` nas últimas N linhas = achado
  (`DATA_PIPELINE_ERROR`); (b) queda de contagem de linhas recentes vs.
  período anterior, calculada pelo próprio campo de timestamp de cada
  linha — sem precisar de estado persistido entre execuções do cron
  (`DATA_ROW_COUNT_DROP`).
- `FonteIdadeArquivo` — idade do arquivo (mtime) vs. cadência máxima
  declarada (`DATA_SOURCE_STALE`).

As duas formas compartilham a distinção "arquivo ausente vs. fonte
desativada" (prova de fogo do pacote): `habilitado=False` pula a fonte
inteira SEM achado nenhum (config, não outage — mesmo padrão de
`FeatureCheck.habilitado`); `habilitado=True` com arquivo ausente no disco
É achado (`DATA_SOURCE_MISSING`, sempre CRITICAL — uma fonte que deveria
existir e não existe é pior do que uma fonte só desatualizada).

Disciplina (contrato de paridade do subsistema `observe`): este módulo
importa `governance` (`SeveridadeAlerta`) + `foundation` + stdlib/pydantic
e NUNCA importa `batman_os.kernel` (ADR-0012), mesma regra de
`feature_manifest.py`.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from batman_os.foundation.types import TenantId
from batman_os.governance.governance_engine import SeveridadeAlerta

_DIR_MANIFESTOS = Path(__file__).resolve().parent / "manifests"


class FonteJsonlPipeline(BaseModel):
    """Uma fonte de dados que é um log JSONL append-only, uma linha por
    execução/lote (ex.: `data/update_log.jsonl` do radar, escrito por
    `scripts/run_pipeline.py` — cada linha final de um pipeline completo
    tem `status` + `steps` (dict nome->"ok"/"skip"/"error"))."""

    id: str
    descricao: str
    arquivo: str  # relativo a `DataSentinelManifest.root_dir`
    campo_status: str = "status"
    valor_ok: str = "ok"
    campo_timestamp: str = "run_at"
    # janela de checagem de status=erro: só as N linhas mais recentes (o
    # arquivo pode ter dezenas de milhares de linhas acumuladas — não
    # relemos o histórico inteiro a cada ciclo de 5min).
    linhas_recentes_para_status: int = 50
    queda_percentual_max: float = 20.0
    # nº mínimo de linhas no período anterior para a checagem de queda
    # fazer sentido (evita "queda de 100%" em fontes com volume naturalmente
    # baixo/ruidoso).
    minimo_linhas_para_checar_queda: int = 5
    severidade_erro: SeveridadeAlerta = SeveridadeAlerta.CRITICAL
    severidade_queda: SeveridadeAlerta = SeveridadeAlerta.WARNING
    habilitado: bool = True
    # Muitas fontes do radar só escrevem em dia útil B3 (`infra/crontab.prod`:
    # a maioria dos jobs usa "1-5", cripto é a exceção 24/7). Comparar
    # "últimas 24h" vs "24h anteriores" cru faria a checagem de QUEDA
    # disparar todo sábado/domingo para essas fontes (queda de ~100% —
    # nenhum job weekday roda). NÃO afeta a checagem de status=erro (uma
    # linha de erro que já existe é achado em qualquer dia).
    dias_uteis_apenas_para_queda: bool = False


class FonteIdadeArquivo(BaseModel):
    """Uma fonte de dados cuja saúde é medida pela IDADE do arquivo
    (mtime) vs. uma cadência máxima declarada — derivada do
    `infra/crontab.prod` do repositório alvo (ex.: `prices_20y.parquet`
    ≤1 pregão, `price_bars` cripto ≤5min)."""

    id: str
    descricao: str
    arquivo: str  # relativo a `DataSentinelManifest.root_dir`
    cadencia_max_minutos: int
    severidade: SeveridadeAlerta = SeveridadeAlerta.WARNING
    habilitado: bool = True
    # Ver `FonteJsonlPipeline.dias_uteis_apenas_para_queda` -- mesmo
    # raciocínio: fontes que só atualizam em dia útil B3 (ex.:
    # prices_20y.parquet, escrito 1x/dia útil às 21h30 UTC) não podem ser
    # cobradas de frescor no sábado/domingo.
    dias_uteis_apenas: bool = False


class DataSentinelManifest(BaseModel):
    """Manifesto declarativo, versionado, por tenant."""

    tenant_id: TenantId
    root_dir: str
    revisado_em: str
    fontes_jsonl: list[FonteJsonlPipeline] = Field(default_factory=list)
    fontes_idade: list[FonteIdadeArquivo] = Field(default_factory=list)


def carregar_manifesto_dados(path: str | Path) -> DataSentinelManifest:
    """Carrega e valida um `DataSentinelManifest` de um arquivo JSON.
    Chaves extra (ex.: `_nota`) são ignoradas — mesma convenção de
    `feature_manifest.py::carregar_manifesto`."""
    dados = json.loads(Path(path).read_text(encoding="utf-8"))
    return DataSentinelManifest.model_validate(dados)


def caminho_manifesto_dados(tenant_id: str) -> Path:
    """Caminho canônico do manifesto de dados de um tenant:
    `manifests/<tenant>_dados.json` ao lado deste módulo — sufixo `_dados`
    para não colidir com `manifests/<tenant>.json` (o `FeatureManifest`
    HTTP de `feature_manifest.py`)."""
    return _DIR_MANIFESTOS / f"{tenant_id}_dados.json"
