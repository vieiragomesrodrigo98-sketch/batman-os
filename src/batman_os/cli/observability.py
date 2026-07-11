"""Vol.II Cap.10 — leitura de observabilidade sobre o Event Bus (Fase 1
do roadmap de plataforma, `.claude/plans/peaceful-wondering-hearth.md`,
item "Mission Timeline"). Só leitura — nunca publica eventos, só formata
o que `EventBus.replay()` já devolve.

Não introduz um `CorrelationId` novo: `MissionId` já é a raiz de
correlação de tudo que uma Missão faz (`EventBus.replay(mission_id)`
já devolve a história causal completa e ordenada de uma Missão — Vol.II
Cap.10, secao 10.2.1). Inventar um segundo identificador de correlação
não agregaria nada além do que `mission_id` já entrega hoje, dado que
cada Missão de scan corresponde a exatamente um (arquivo, regra)."""

from __future__ import annotations

from batman_os.foundation.types import MissionId, TenantId
from batman_os.kernel.event_bus import EventBus, KernelEvent


def linha_do_tempo(event_bus: EventBus, mission_id: MissionId, tenant_id: TenantId) -> list[str]:
    """A "Mission Timeline" do roadmap de plataforma — replay causal de
    uma Missão (Vol.II Cap.10), formatado como linhas legíveis na ordem
    de publicação.

    `tenant_id` (Fase 5 do roadmap de plataforma, `.claude/plans/
    peaceful-wondering-hearth.md`, Estagio 5.1) — só inclui eventos cujo
    `tenant_id` bate com o solicitado; Missão de outro tenant produz o
    MESMO resultado que Missão inexistente (lista vazia), nunca uma
    exceção distinta que revelaria existência cross-tenant. Esta função
    lê o `EventBus` diretamente (não passa por `MissionRuntime.
    get_mission()`), então precisa da própria checagem."""
    return [
        _formatar_evento(evento)
        for evento in event_bus.replay(mission_id)
        if evento.tenant_id == tenant_id
    ]


def _formatar_evento(evento: KernelEvent) -> str:
    extras = {chave: valor for chave, valor in evento.payload.items() if chave != "estado"}
    sufixo = (
        f" ({', '.join(f'{chave}={valor}' for chave, valor in extras.items())})" if extras else ""
    )
    return f"{evento.ocorrido_em.isoformat()} {evento.tipo}{sufixo}"
