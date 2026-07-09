"""Testes do handler bespoke REV-005 "bloco de código duplicado"
(`rev005_bloco_duplicado.py`)."""

from __future__ import annotations

import json

from batman_os.capabilities.operator import ExecutionContext
from batman_os.capabilities.rules.rev005_bloco_duplicado import avaliar_rev005
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
        "codigo": "REV-005",
        "agente": "code-reviewer",
        "severidade": "low",
        "categoria": "manutenibilidade",
        "titulo": "titulo",
        "causa": "causa",
        "remediacao": "remediacao",
    }


class TestBlocoDuplicado:
    def test_dispara_para_bloco_de_8_linhas_duplicado_entre_arquivos(self) -> None:
        bloco = "\n".join(f"linha_{i} = {i}" for i in range(10))
        entrada = {
            "caminho": ".",
            "conteudo": json.dumps({"arquivos": {"a.py": bloco, "b.py": bloco}}),
            "regra": _regra(),
        }
        saida = avaliar_rev005(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_para_arquivos_sem_bloco_em_comum(self) -> None:
        entrada = {
            "caminho": ".",
            "conteudo": json.dumps({"arquivos": {"a.py": "x = 1\n", "b.py": "y = 2\n"}}),
            "regra": _regra(),
        }
        saida = avaliar_rev005(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_para_bloco_repetido_dentro_do_mesmo_arquivo(self) -> None:
        bloco = "\n".join(f"linha_{i} = {i}" for i in range(10))
        entrada = {
            "caminho": ".",
            "conteudo": json.dumps({"arquivos": {"a.py": bloco + "\n" + bloco}}),
            "regra": _regra(),
        }
        saida = avaliar_rev005(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_para_bloco_de_import(self) -> None:
        bloco = "\n".join(f"import modulo_{i}" for i in range(10))
        entrada = {
            "caminho": ".",
            "conteudo": json.dumps({"arquivos": {"a.py": bloco, "b.py": bloco}}),
            "regra": _regra(),
        }
        saida = avaliar_rev005(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_sem_conteudo(self) -> None:
        entrada = {"caminho": ".", "conteudo": None, "regra": _regra()}
        saida = avaliar_rev005(entrada, _contexto())
        assert saida["achados"] == []

    def test_de_dup_global_por_par_de_arquivos(self) -> None:
        bloco_a = "\n".join(f"linha_{i} = {i}" for i in range(10))
        bloco_b = "\n".join(f"outra_{i} = {i}" for i in range(10))
        conteudo_x = bloco_a + "\n" + bloco_b
        entrada = {
            "caminho": ".",
            "conteudo": json.dumps({"arquivos": {"x.py": conteudo_x, "y.py": conteudo_x}}),
            "regra": _regra(),
        }
        saida = avaliar_rev005(entrada, _contexto())
        # duas janelas distintas batem entre os mesmos 2 arquivos -- so 1
        # achado (de-dup global por par de arquivos, nao por hash de janela)
        assert len(saida["achados"]) == 1
