"""Vol. IV, Cap. 19 — Cooperação entre Operadores.

Fecha o Volume IV: como múltiplos Operadores cooperam dentro de uma mesma
Missão. Regra estrutural: nenhum Operador chama outro diretamente — toda
cooperação passa pelo Workflow Engine (pipeline/fan-out/fan-in via grafo de
dependências, já implementado no Vol.II Cap.9) ou por sub-missão governada.

Fonte da verdade: docs/spec/04-capabilities/05-cooperation.md
"""

from __future__ import annotations

from batman_os.capabilities.operator import Operator
from batman_os.foundation.types import MissionTypeId

# Excecao deliberada ao grafo de dependencias do Vol.VIII Cap.32, secao 32.3
# (capabilities -> shared/runtime, nunca -> kernel). Cooperacao por
# sub-missao (secao 19.3.3 deste capitulo) e, por definicao, um Operador
# (capabilities) criando uma Missao (kernel/Mission Runtime, Cap.6) — a
# propria natureza do padrao exige essa dependencia. O diagrama do Cap.32
# nao desenha a aresta capabilities->kernel; entendido como uma lacuna no
# diagrama daquele capitulo (escrito depois deste), nao um erro de codigo
# aqui (achado de revisao, decisao do autor: manter e documentar, nao
# ofuscar com um Protocol local que nao reduziria o acoplamento real).
from batman_os.kernel.mission_runtime import Mission, MissionIntent, MissionRuntime


class ReferenciaDiretaEntreOperadoresDetectada(Exception):
    """Vol.IV Cap.19, secao 19.4/19.5 (AT-19.1) — Operador possui, em seus
    próprios atributos, uma referência direta a outro Operador. Violação
    estrutural (Cap.15, secao 15.3: um Operador só recebe `ExecutionContext`
    mínimo, nunca outro Operador)."""


def auditar_ausencia_de_referencia_direta(operador: Operator) -> None:
    """Vol.IV Cap.19, secao 19.5 (AT-19.1) — auditoria estática: nenhum
    atributo do Operador (direto ou dentro de listas/tuplas/sets) pode ser,
    ele mesmo, uma instância de `Operator` — o que caracterizaria
    acoplamento direto, bypass do Workflow Engine (secao 19.2)."""
    for nome, valor in vars(operador).items():
        if isinstance(valor, Operator):
            raise ReferenciaDiretaEntreOperadoresDetectada(
                f"Operador '{operador.id}' tem referencia direta a outro Operador "
                f"no atributo '{nome}' — cooperacao deve ser mediada pelo Workflow Engine"
            )
        if isinstance(valor, list | tuple | set):
            for item in valor:
                if isinstance(item, Operator):
                    raise ReferenciaDiretaEntreOperadoresDetectada(
                        f"Operador '{operador.id}' tem referencia direta a outro Operador "
                        f"dentro da colecao '{nome}' — cooperacao deve ser mediada pelo "
                        "Workflow Engine"
                    )


def criar_submissao(
    mission_runtime: MissionRuntime,
    missao_pai: Mission,
    intent: MissionIntent,
    tipo: MissionTypeId,
) -> Mission:
    """Vol.IV Cap.19, secao 19.3.3 (AT-19.3) — cria uma sub-missão que herda
    OBRIGATORIAMENTE o `tenant_id` da missão pai (nunca um valor diferente ou
    explícito por chamador), garantindo isolamento consistente (ADR-0005,
    Vol.III Cap.14) e auditoria independente via `replay` (Vol.II Cap.10).

    Esta é a única forma correta de um Operador "iniciar um novo fluxo de
    trabalho independente" — nunca invocação direta de outro Operador."""
    return mission_runtime.create(
        intent=intent,
        tipo=tipo,
        tenant_id=missao_pai.tenant_id,
        parent_mission_id=missao_pai.id,
    )
