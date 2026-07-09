"""Testes do handler bespoke PD-010 "simulador sem bloqueio de saldo
mínimo" (`pd010_simulador_sem_piso.py`)."""

from __future__ import annotations

from batman_os.capabilities.operator import ExecutionContext
from batman_os.capabilities.rules.pd010_simulador_sem_piso import avaliar_pd010
from batman_os.foundation.types import MissionId, StepId, TenantId, agora


def _contexto() -> ExecutionContext:
    return ExecutionContext(
        mission_id=MissionId("m-1"),
        tenant_id=TenantId("t-1"),
        step_id=StepId("s-1"),
        deadline=agora(),
    )


def _regra(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "codigo": "PD-010",
        "agente": "product-designer",
        "severidade": "medium",
        "categoria": "regra-de-negocio",
        "titulo": "titulo",
        "causa": "causa",
        "remediacao": "remediacao",
        "sim_router_path": "api/routers/sim.py",
    }
    base.update(overrides)
    return base


class TestSimuladorSemPiso:
    def test_dispara_para_backend_sem_piso_de_saldo(self) -> None:
        entrada = {
            "caminho": "api/routers/sim.py",
            "conteudo": "def abrir_posicao():\n    pass\n",
            "regra": _regra(),
        }
        saida = avaliar_pd010(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_para_backend_com_piso_de_saldo(self) -> None:
        entrada = {
            "caminho": "api/routers/sim.py",
            "conteudo": "MIN_TRADE_CAPITAL = 10\n",
            "regra": _regra(),
        }
        saida = avaliar_pd010(entrada, _contexto())
        assert saida["achados"] == []

    def test_dispara_para_frontend_de_simulador_sem_desabilitar_botao(self) -> None:
        entrada = {
            "caminho": "frontend/src/SimuladorFree.tsx",
            "conteudo": "const balance = 0;\nreturn <button>Comprar</button>;\n",
            "regra": _regra(),
        }
        saida = avaliar_pd010(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_para_frontend_que_desabilita_botao(self) -> None:
        entrada = {
            "caminho": "frontend/src/SimuladorFree.tsx",
            "conteudo": (
                "const balance = 0;\nreturn <button disabled={balance < MIN}>Comprar</button>;\n"
            ),
            "regra": _regra(),
        }
        saida = avaliar_pd010(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_para_frontend_sem_mencao_a_saldo(self) -> None:
        entrada = {
            "caminho": "frontend/src/SimuladorFree.tsx",
            "conteudo": "return <div>Ola</div>;\n",
            "regra": _regra(),
        }
        saida = avaliar_pd010(entrada, _contexto())
        assert saida["achados"] == []
