"""Testes do handler bespoke SEC-008 "endpoint de role sem guarda
super_admin" (`sec008_role_sem_super_admin.py`)."""

from __future__ import annotations

from batman_os.capabilities.operator import ExecutionContext
from batman_os.capabilities.rules.sec008_role_sem_super_admin import avaliar_sec008
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
        "codigo": "SEC-008",
        "agente": "security-engineer",
        "severidade": "high",
        "categoria": "access-control",
        "titulo": "titulo",
        "causa": "causa",
        "remediacao": "remediacao",
    }


class TestRoleSemSuperAdmin:
    def test_dispara_para_rota_com_role_no_path_sem_super_admin(self) -> None:
        entrada = {
            "caminho": "api/routers/usuarios.py",
            "conteudo": (
                '@router.patch("/usuarios/{id}/role")\n'
                "def alterar_role(id: int, role: str, _=Depends(require_admin)):\n"
                "    pass\n"
            ),
            "regra": _regra(),
        }
        saida = avaliar_sec008(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_dispara_para_role_na_assinatura_sem_super_admin(self) -> None:
        entrada = {
            "caminho": "api/routers/usuarios.py",
            "conteudo": (
                '@router.patch("/usuarios/{id}")\n'
                "def alterar(id: int, role: str, _=Depends(require_admin)):\n"
                "    pass\n"
            ),
            "regra": _regra(),
        }
        saida = avaliar_sec008(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_com_verificacao_super_admin(self) -> None:
        entrada = {
            "caminho": "api/routers/usuarios.py",
            "conteudo": (
                '@router.patch("/usuarios/{id}/role")\n'
                "def alterar_role(id: int, role: str, _=Depends(require_admin)):\n"
                "    if current.role != 'super_admin':\n"
                "        raise HTTPException(403)\n"
            ),
            "regra": _regra(),
        }
        saida = avaliar_sec008(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_sem_require_admin(self) -> None:
        entrada = {
            "caminho": "api/routers/usuarios.py",
            "conteudo": (
                '@router.patch("/usuarios/{id}/role")\ndef alterar(id: int, role: str):\n    pass\n'
            ),
            "regra": _regra(),
        }
        saida = avaliar_sec008(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_sem_role_no_path_ou_assinatura(self) -> None:
        entrada = {
            "caminho": "api/routers/usuarios.py",
            "conteudo": (
                '@router.patch("/usuarios/{id}")\n'
                "def alterar(id: int, nome: str, _=Depends(require_admin)):\n"
                "    pass\n"
            ),
            "regra": _regra(),
        }
        saida = avaliar_sec008(entrada, _contexto())
        assert saida["achados"] == []
