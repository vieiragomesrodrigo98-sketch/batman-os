"""Testes de `cli/inbox_command.py` — orquestradores testáveis do `batman
inbox` (`executar_inbox_list/ack/defer` + `resolver_db_path_inbox`)."""

from __future__ import annotations

from pathlib import Path

import pytest

from batman_os.cli.inbox_command import (
    executar_inbox_ack,
    executar_inbox_defer,
    executar_inbox_list,
    resolver_db_path_inbox,
)
from batman_os.foundation.types import Criticidade, TenantId
from batman_os.governance.inbox import (
    AchadoInboxDesconhecido,
    AchadoInboxEntrada,
    InboxStore,
    NotaObrigatoria,
    OrigemAchado,
)


def _semear(db_path: str, tenant_id: TenantId | None = None) -> str:
    tenant_id = tenant_id or TenantId("acme")
    with InboxStore(db_path) as store:
        store.ingest(
            [
                AchadoInboxEntrada(
                    chave_dominio="CTO-002|src/x.py|",
                    severidade=Criticidade.HIGH,
                    titulo="timeout ausente",
                    detalhe="chamada sem timeout",
                )
            ],
            origem=OrigemAchado.SCAN,
            tenant_id=tenant_id,
        )
        return store.listar()[0].id


class TestExecutarInboxList:
    def test_lista_achados_novos(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "estado.db")
        _semear(db_path)

        achados = executar_inbox_list(db_path)
        assert len(achados) == 1

    def test_apenas_novos_false_inclui_tratados(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "estado.db")
        achado_id = _semear(db_path)
        executar_inbox_ack(db_path, achado_id, "corrigido")

        assert executar_inbox_list(db_path) == []
        assert len(executar_inbox_list(db_path, apenas_novos=False)) == 1

    def test_filtro_por_tenant(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "estado.db")
        _semear(db_path, tenant_id=TenantId("acme"))
        _semear(db_path, tenant_id=TenantId("outro"))

        assert len(executar_inbox_list(db_path)) == 2
        assert len(executar_inbox_list(db_path, tenant_id=TenantId("acme"))) == 1


class TestExecutarInboxAckDefer:
    def test_ack_marca_tratado(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "estado.db")
        achado_id = _semear(db_path)

        achado = executar_inbox_ack(db_path, achado_id, "fix no commit x")
        assert achado.status.value == "tratado"

    def test_defer_marca_deferido(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "estado.db")
        achado_id = _semear(db_path)

        achado = executar_inbox_defer(db_path, achado_id, "aceito o risco por ora")
        assert achado.status.value == "deferido"

    def test_ack_sem_nota_propaga_nota_obrigatoria(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "estado.db")
        achado_id = _semear(db_path)

        with pytest.raises(NotaObrigatoria):
            executar_inbox_ack(db_path, achado_id, "")

    def test_ack_id_desconhecido_propaga_excecao(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "estado.db")
        _semear(db_path)

        with pytest.raises(AchadoInboxDesconhecido):
            executar_inbox_ack(db_path, "id-fantasma", "nota")


class TestResolverDbPathInbox:
    def test_db_explicito_vence(self) -> None:
        assert resolver_db_path_inbox("/tmp/custom.db") == "/tmp/custom.db"

    def test_default_relativo_ao_cwd(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)

        resolvido = resolver_db_path_inbox(None)

        assert resolvido == str(Path(".batman-os") / "estado.db")
        assert (tmp_path / ".batman-os").exists()
