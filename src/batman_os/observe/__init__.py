"""Anexo ao Vol.VII Cap.27/30 — subsistema `observe` (watcher/daemon).

Paridade-ou-melhor sobre o observe/daemon do Batman legado
(`radar-preditivo/Batman/observe/`), unificado numa fonte canonica de
regras (fix BATBL-007). Ver `docs/observe/PARIDADE_OBSERVE.md`.

Disciplina (contrato de paridade): importa `governance` + `foundation` +
stdlib/psutil; NUNCA importa `batman_os.kernel` (ADR-0012). Entrega via
`governance.alert_sinks` (ja feito) — este pacote nao reimplementa entrega.
"""

from __future__ import annotations

from batman_os.observe.collectors import (
    EndpointCollectorUrllib,
    InfraCollectorPsutil,
    LogCollectorTail,
    PortCollectorPsutil,
    ProcessCollectorPsutil,
)
from batman_os.observe.feature_manifest import (
    AuthConfig,
    DriftConfig,
    FeatureCheck,
    FeatureManifest,
    ResultadoConteudo,
    avaliar_conteudo,
    caminho_manifesto,
    carregar_manifesto,
)
from batman_os.observe.functional_monitor import (
    CredenciaisDoAmbiente,
    FunctionalMonitor,
    RespostaSonda,
    SondadorUrllib,
)
from batman_os.observe.snapshot import (
    AmostraAuth,
    AmostraEndpoint,
    AmostraInfra,
    AmostraPortas,
    ContagemNginx,
    ObserveSnapshot,
    PortaEscuta,
)
from batman_os.observe.watcher import ObserveWatcher

__all__ = [
    "AmostraAuth",
    "AmostraEndpoint",
    "AmostraInfra",
    "AmostraPortas",
    "AuthConfig",
    "ContagemNginx",
    "CredenciaisDoAmbiente",
    "DriftConfig",
    "EndpointCollectorUrllib",
    "FeatureCheck",
    "FeatureManifest",
    "FunctionalMonitor",
    "InfraCollectorPsutil",
    "LogCollectorTail",
    "ObserveSnapshot",
    "ObserveWatcher",
    "PortCollectorPsutil",
    "PortaEscuta",
    "ProcessCollectorPsutil",
    "RespostaSonda",
    "ResultadoConteudo",
    "SondadorUrllib",
    "avaliar_conteudo",
    "caminho_manifesto",
    "carregar_manifesto",
]
