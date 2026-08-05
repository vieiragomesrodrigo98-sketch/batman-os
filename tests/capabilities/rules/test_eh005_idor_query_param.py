"""Testes de comportamento do spec EH-005 (`specs/lote_02/EH-005.json`)
contra o handler genérico — paridade com o legado ENDURECIDO (commit
`c4f1f5d6`): só flagra `user_id` que seja Query param do MESMO parâmetro
(`user_id: ... = Query(`), não mais "qualquer `user_id:` + qualquer
`Query(` em pontos distintos do arquivo" (falso positivo real:
`api/routers/carteira.py` — assinatura de helper privado + Query de
paginação de outro endpoint)."""

from __future__ import annotations

from typing import Any

from batman_os.capabilities.operator import ExecutionContext
from batman_os.capabilities.rules.lote_02 import carregar_lote_02
from batman_os.capabilities.rules.regex_sobre_conteudo import RegraSpec, avaliar_regra_regex
from batman_os.foundation.types import MissionId, StepId, TenantId, agora


def _contexto() -> ExecutionContext:
    return ExecutionContext(
        mission_id=MissionId("m-1"),
        tenant_id=TenantId("t-1"),
        step_id=StepId("s-1"),
        deadline=agora(),
    )


def _regra_eh005() -> RegraSpec:
    [item] = [i for i in carregar_lote_02() if i["regra"].codigo == "EH-005"]
    regra: RegraSpec = item["regra"]
    return regra


def _avaliar(conteudo: str) -> Any:
    entrada = {
        "caminho": "api/routers/carteira.py",
        "conteudo": conteudo,
        "regra": _regra_eh005().model_dump(),
    }
    return avaliar_regra_regex(entrada, _contexto())


class TestDisparo:
    def test_dispara_para_user_id_query_param_sem_ownership(self) -> None:
        saida = _avaliar(
            "@router.get('/posicoes')\n"
            "def listar(user_id: int = Query(...)):\n"
            "    return buscar(user_id)\n"
        )
        assert len(saida["achados"]) == 1

    def test_nao_dispara_para_user_id_de_helper_com_query_nao_relacionado(self) -> None:
        # O caso exato do falso positivo do legado pré-c4f1f5d6:
        # `user_id: int` numa assinatura privada + `Query(` de paginação
        # em OUTRO endpoint do mesmo arquivo.
        saida = _avaliar(
            "def _decrypt_posicao(row, user_id: int):\n"
            "    return row\n"
            "\n"
            "@router.get('/posicoes')\n"
            "def listar(limit: int = Query(10), offset: int = Query(0)):\n"
            "    return paginar(limit, offset)\n"
        )
        assert saida["achados"] == []

    def test_nao_dispara_quando_ha_require_admin(self) -> None:
        saida = _avaliar(
            "@router.get('/posicoes', dependencies=[Depends(require_admin)])\n"
            "def listar(user_id: int = Query(...)):\n"
            "    return buscar(user_id)\n"
        )
        assert saida["achados"] == []

    def test_nao_dispara_quando_ha_ownership_check(self) -> None:
        saida = _avaliar(
            "@router.get('/posicoes')\n"
            "def listar(user_id: int = Query(...)):\n"
            "    if user_id != current_user.id:\n"
            "        raise HTTPException(403)\n"
            "    return buscar(user_id)\n"
        )
        assert saida["achados"] == []

    def test_nao_dispara_quando_igualdade_quebrada_em_duas_linhas(self) -> None:
        # o legado casa o escopo LINHA a LINHA (`grep_lines`) — o `=` e o
        # `Query(` precisam estar na mesma linha do `user_id:`.
        saida = _avaliar(
            "@router.get('/posicoes')\ndef listar(user_id: int =\n        Query(...)):\n    pass\n"
        )
        assert saida["achados"] == []
