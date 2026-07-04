"""Vol. VI, Cap. 24/26 — adaptador entre Rule Evolution e o Decision Engine.

Achado de revisão: `rule_evolution.py::resolve_rule()` existia e era testada
isoladamente, mas nunca era de fato consultada pelo `DecisionEngine`
(Vol.II Cap.8) — uma `RuleDefinition` promovida a `active` nunca chegava a
influenciar uma decisão real, apesar do ciclo completo estar descrito no
diagrama do Cap.26, secao 26.2 ("Decision Engine consulta conhecimento
atualizado").

Excecao deliberada ao grafo de dependencias do Vol.VIII Cap.32, secao 32.3
(mesmo raciocinio de `capabilities/cooperation.py`): a FUNCAO deste modulo
é ser a ponte entre `learning/` e `kernel/` — bridging code inerentemente
precisa importar dos dois lados. `rule_evolution.py` em si permanece
desacoplado do kernel (usa `DecisionPointComoAssinatura`, um Protocol);
só este adaptador, cuja unica razao de existir e a integracao, importa
`kernel.decision_engine`/`kernel.planning_engine` diretamente.

Limitacao documentada: `DecisionPoint` (Vol.II Cap.7) nao carrega um
payload generico de dados (`dados: dict`) — `RuleCondition`s alem do
casamento por `pergunta` (Cap.24, secao 24.2) nao podem ser avaliadas por
este adaptador ainda; passa sempre `dados={}`, o que so casa regras com
`condition` vazio. Fechar essa lacuna exigiria estender `DecisionPoint`
com um payload generico — mudanca de modelagem do Cap.7, fora do escopo
deste adaptador.
"""

from __future__ import annotations

from batman_os.foundation.types import Evidence
from batman_os.kernel.decision_engine import ResolucaoConhecimento
from batman_os.kernel.planning_engine import DecisionPoint
from batman_os.learning.rule_evolution import RuleDefinition, resolve_rule


class CatalogoDeRegrasComoBaseConhecimento:
    """Vol.VI Cap.26, secao 26.2 — implementa `BaseConhecimento` (Vol.II
    Cap.8) usando `resolve_rule()` (Cap.24) sobre um catálogo de
    `RuleDefinition`s ativas. É isto que fecha o ciclo: uma regra
    promovida via shadow mode (Cap.24) passa a ser, de fato, consultada
    pelo Decision Engine na próxima missão do mesmo padrão."""

    def __init__(self, regras: list[RuleDefinition]) -> None:
        self._regras = regras

    def consultar(self, ponto: DecisionPoint) -> ResolucaoConhecimento | None:
        regra = resolve_rule(ponto, dados={}, candidatos=self._regras)
        if regra is None:
            return None
        return ResolucaoConhecimento(
            opcao=regra.resolution,
            confidence=regra.confidence_base,
            evidencia=[
                Evidence(
                    origem=f"RuleDefinition:{regra.id}",
                    evidencias=[
                        f"version={regra.version}",
                        f"reviewedBy={regra.provenance.reviewed_by}",
                    ],
                    confianca=regra.confidence_base,
                )
            ],
        )
