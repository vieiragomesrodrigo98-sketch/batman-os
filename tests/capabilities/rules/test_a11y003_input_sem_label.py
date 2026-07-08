"""Testes do handler bespoke A11Y-003 "<input> sem label associado"
(`a11y003_input_sem_label.py`)."""

from __future__ import annotations

from batman_os.capabilities.operator import ExecutionContext
from batman_os.capabilities.rules.a11y003_input_sem_label import avaliar_a11y003
from batman_os.foundation.types import MissionId, StepId, TenantId, agora


def _contexto() -> ExecutionContext:
    return ExecutionContext(
        mission_id=MissionId("m-1"),
        tenant_id=TenantId("t-1"),
        step_id=StepId("s-1"),
        deadline=agora(),
    )


def _regra() -> dict[str, object]:
    return {
        "codigo": "A11Y-003",
        "agente": "accessibility-specialist",
        "severidade": "medium",
        "categoria": "acessibilidade",
        "titulo": "titulo",
        "causa": "causa",
        "remediacao": "remediacao",
    }


class TestInputSemLabel:
    def test_dispara_para_input_sem_label_nem_aria(self) -> None:
        entrada = {
            "caminho": "frontend/src/Form.tsx",
            "conteudo": '<div>\n<input type="text" />\n</div>\n',
            "regra": _regra(),
        }
        saida = avaliar_a11y003(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_com_aria_label_na_tag(self) -> None:
        entrada = {
            "caminho": "frontend/src/Form.tsx",
            "conteudo": '<div>\n<input type="text" aria-label="Nome" />\n</div>\n',
            "regra": _regra(),
        }
        saida = avaliar_a11y003(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_com_aria_label_na_vizinhanca(self) -> None:
        entrada = {
            "caminho": "frontend/src/Form.tsx",
            "conteudo": ('<input type="text"\n  onChange={e => set(e)}\n  aria-label="Nome"\n/>\n'),
            "regra": _regra(),
        }
        saida = avaliar_a11y003(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_com_label_htmlfor_em_qualquer_lugar_do_arquivo(self) -> None:
        entrada = {
            "caminho": "frontend/src/Form.tsx",
            "conteudo": ('<label htmlFor="x">Nome</label>\n<div>\n<input type="text" />\n</div>\n'),
            "regra": _regra(),
        }
        saida = avaliar_a11y003(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_com_label_wrapper_implicito_acima(self) -> None:
        entrada = {
            "caminho": "frontend/src/Form.tsx",
            "conteudo": '<label>\nNome\n<input type="text" />\n</label>\n',
            "regra": _regra(),
        }
        saida = avaliar_a11y003(entrada, _contexto())
        assert saida["achados"] == []

    def test_ignora_input_hidden(self) -> None:
        entrada = {
            "caminho": "frontend/src/Form.tsx",
            "conteudo": '<input type="hidden" name="csrf" />\n',
            "regra": _regra(),
        }
        saida = avaliar_a11y003(entrada, _contexto())
        assert saida["achados"] == []

    def test_multiplos_inputs_sem_label_agregam_num_unico_achado(self) -> None:
        entrada = {
            "caminho": "frontend/src/Form.tsx",
            "conteudo": '<input type="text" />\n<input type="email" />\n',
            "regra": _regra(),
        }
        saida = avaliar_a11y003(entrada, _contexto())
        assert len(saida["achados"]) == 1
        assert "1" in saida["achados"][0]["descricao"]
        assert "2" in saida["achados"][0]["descricao"]
