"""Testes da fila persistente de achados ("inbox", `governance/inbox.py`).

Cobre: modelo/upsert/idempotência (ponto 1 do pacote), transições de status
(ponto 3), nota obrigatória, e persistência real via SQLite em disco (ponto
2 — mesma infraestrutura de `--db` do `EventBus`/`OperationalMemory`)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from batman_os.foundation.types import Criticidade, TenantId
from batman_os.governance.governance_engine import SeveridadeAlerta
from batman_os.governance.inbox import (
    AchadoInboxDesconhecido,
    AchadoInboxEntrada,
    InboxStore,
    NotaObrigatoria,
    OrigemAchado,
    StatusAchadoInbox,
    calcular_id_estavel,
    mapear_severidade_alerta,
)

TENANT = TenantId("acme")
OUTRO_TENANT = TenantId("outro")


def _entrada(
    chave: str = "CTO-002|src/x.py|",
    severidade: Criticidade = Criticidade.HIGH,
    titulo: str = "titulo",
    detalhe: str = "detalhe",
) -> AchadoInboxEntrada:
    return AchadoInboxEntrada(
        chave_dominio=chave, severidade=severidade, titulo=titulo, detalhe=detalhe
    )


class TestCalcularIdEstavel:
    def test_mesma_tripla_produz_o_mesmo_id_sempre(self) -> None:
        id1 = calcular_id_estavel(OrigemAchado.SCAN, TENANT, "CTO-002|src/x.py|")
        id2 = calcular_id_estavel(OrigemAchado.SCAN, TENANT, "CTO-002|src/x.py|")
        assert id1 == id2

    def test_chave_dominio_diferente_produz_id_diferente(self) -> None:
        id1 = calcular_id_estavel(OrigemAchado.SCAN, TENANT, "CTO-002|src/x.py|")
        id2 = calcular_id_estavel(OrigemAchado.SCAN, TENANT, "CTO-002|src/y.py|")
        assert id1 != id2

    def test_origem_diferente_produz_id_diferente(self) -> None:
        id1 = calcular_id_estavel(OrigemAchado.SCAN, TENANT, "x")
        id2 = calcular_id_estavel(OrigemAchado.MONITOR, TENANT, "x")
        assert id1 != id2

    def test_tenant_diferente_produz_id_diferente(self) -> None:
        id1 = calcular_id_estavel(OrigemAchado.SCAN, TENANT, "x")
        id2 = calcular_id_estavel(OrigemAchado.SCAN, OUTRO_TENANT, "x")
        assert id1 != id2


class TestIngestUpsertIdempotente:
    def test_primeira_ingestao_insere_como_novo(self) -> None:
        store = InboxStore()
        resumo = store.ingest([_entrada()], origem=OrigemAchado.SCAN, tenant_id=TENANT)

        assert resumo.novos == 1
        assert resumo.atualizados == 0
        achados = store.listar()
        assert len(achados) == 1
        assert achados[0].status == StatusAchadoInbox.NOVO

    def test_reingestao_do_mesmo_achado_nao_duplica_faz_upsert(self) -> None:
        store = InboxStore()
        store.ingest([_entrada()], origem=OrigemAchado.SCAN, tenant_id=TENANT)
        resumo2 = store.ingest([_entrada()], origem=OrigemAchado.SCAN, tenant_id=TENANT)

        assert resumo2.novos == 0
        assert resumo2.atualizados == 1
        assert len(store.listar()) == 1

    def test_reingestao_com_titulo_novo_atualiza_conteudo_sem_duplicar(self) -> None:
        store = InboxStore()
        store.ingest([_entrada(titulo="titulo velho")], origem=OrigemAchado.SCAN, tenant_id=TENANT)
        store.ingest([_entrada(titulo="titulo novo")], origem=OrigemAchado.SCAN, tenant_id=TENANT)

        achados = store.listar()
        assert len(achados) == 1
        assert achados[0].titulo == "titulo novo"

    def test_achado_abaixo_do_limiar_nao_entra_na_fila(self) -> None:
        store = InboxStore()
        resumo = store.ingest(
            [_entrada(severidade=Criticidade.LOW)],
            origem=OrigemAchado.SCAN,
            tenant_id=TENANT,
            limiar=Criticidade.MEDIUM,
        )

        assert resumo.novos == 0
        assert store.listar(apenas_novos=False) == []

    def test_achado_no_limiar_exato_entra_na_fila(self) -> None:
        store = InboxStore()
        resumo = store.ingest(
            [_entrada(severidade=Criticidade.MEDIUM)],
            origem=OrigemAchado.SCAN,
            tenant_id=TENANT,
            limiar=Criticidade.MEDIUM,
        )
        assert resumo.novos == 1

    def test_tenants_diferentes_nao_colidem(self) -> None:
        store = InboxStore()
        store.ingest([_entrada()], origem=OrigemAchado.SCAN, tenant_id=TENANT)
        store.ingest([_entrada()], origem=OrigemAchado.SCAN, tenant_id=OUTRO_TENANT)

        assert len(store.listar()) == 2
        assert len(store.listar(tenant_id=TENANT)) == 1
        assert len(store.listar(tenant_id=OUTRO_TENANT)) == 1


class TestAutoResolucao:
    def test_achado_ausente_na_proxima_ingestao_e_marcado_resolvido(self) -> None:
        store = InboxStore()
        store.ingest([_entrada(chave="A")], origem=OrigemAchado.SCAN, tenant_id=TENANT)

        resumo = store.ingest([], origem=OrigemAchado.SCAN, tenant_id=TENANT)

        assert resumo.resolvidos_automaticamente == 1
        assert store.listar() == []  # nao aparece na lista default (so 'novo')
        todos = store.listar(apenas_novos=False)
        assert len(todos) == 1
        assert todos[0].status == StatusAchadoInbox.RESOLVIDO

    def test_resolvido_nao_e_marcado_resolvido_de_novo(self) -> None:
        store = InboxStore()
        store.ingest([_entrada(chave="A")], origem=OrigemAchado.SCAN, tenant_id=TENANT)
        store.ingest([], origem=OrigemAchado.SCAN, tenant_id=TENANT)

        resumo3 = store.ingest([], origem=OrigemAchado.SCAN, tenant_id=TENANT)
        assert resumo3.resolvidos_automaticamente == 0

    def test_achado_resolvido_que_reaparece_volta_para_novo(self) -> None:
        store = InboxStore()
        store.ingest([_entrada(chave="A")], origem=OrigemAchado.SCAN, tenant_id=TENANT)
        store.ingest([], origem=OrigemAchado.SCAN, tenant_id=TENANT)  # resolve

        store.ingest([_entrada(chave="A")], origem=OrigemAchado.SCAN, tenant_id=TENANT)  # regressao

        achados = store.listar()
        assert len(achados) == 1
        assert achados[0].status == StatusAchadoInbox.NOVO
        assert achados[0].tratado_em is None

    def test_mudanca_de_limiar_nao_resolve_achado_que_so_ficou_abaixo_do_novo_corte(
        self,
    ) -> None:
        store = InboxStore()
        entrada_baixa = _entrada(chave="A", severidade=Criticidade.LOW)
        store.ingest(
            [entrada_baixa], origem=OrigemAchado.SCAN, tenant_id=TENANT, limiar=Criticidade.LOW
        )
        assert len(store.listar()) == 1

        # mesmo achado, ainda presente na entrada, mas agora abaixo do limiar
        resumo = store.ingest(
            [entrada_baixa], origem=OrigemAchado.SCAN, tenant_id=TENANT, limiar=Criticidade.MEDIUM
        )

        assert resumo.resolvidos_automaticamente == 0
        assert len(store.listar()) == 1  # continua novo, nao foi resolvido por engano

    def test_tratado_que_some_e_resolvido_automaticamente(self) -> None:
        store = InboxStore()
        store.ingest([_entrada(chave="A")], origem=OrigemAchado.SCAN, tenant_id=TENANT)
        achado_id = store.listar()[0].id
        store.ack(achado_id, "corrigido em commit x")

        resumo = store.ingest([], origem=OrigemAchado.SCAN, tenant_id=TENANT)

        assert resumo.resolvidos_automaticamente == 1
        achado = store.obter(achado_id)
        assert achado.status == StatusAchadoInbox.RESOLVIDO

    def test_origem_diferente_nao_interfere_na_resolucao(self) -> None:
        store = InboxStore()
        store.ingest([_entrada(chave="A")], origem=OrigemAchado.SCAN, tenant_id=TENANT)
        store.ingest([_entrada(chave="A")], origem=OrigemAchado.MONITOR, tenant_id=TENANT)

        # ingestao vazia so do MONITOR nao deve resolver o achado do SCAN
        resumo = store.ingest([], origem=OrigemAchado.MONITOR, tenant_id=TENANT)

        assert resumo.resolvidos_automaticamente == 1
        restantes = store.listar()
        assert len(restantes) == 1
        assert restantes[0].origem == OrigemAchado.SCAN


class TestTransicoesDeStatus:
    def test_ack_marca_tratado_com_nota_e_timestamp(self) -> None:
        store = InboxStore()
        store.ingest([_entrada()], origem=OrigemAchado.SCAN, tenant_id=TENANT)
        achado_id = store.listar()[0].id

        achado = store.ack(achado_id, "fix aplicado no commit abc123")

        assert achado.status == StatusAchadoInbox.TRATADO
        assert achado.nota == "fix aplicado no commit abc123"
        assert achado.tratado_em is not None

    def test_defer_marca_deferido_com_nota(self) -> None:
        store = InboxStore()
        store.ingest([_entrada()], origem=OrigemAchado.SCAN, tenant_id=TENANT)
        achado_id = store.listar()[0].id

        achado = store.defer(achado_id, "aceito o risco por ora, revisar em Q3")

        assert achado.status == StatusAchadoInbox.DEFERIDO
        assert achado.nota == "aceito o risco por ora, revisar em Q3"

    def test_ack_sem_nota_levanta_nota_obrigatoria(self) -> None:
        store = InboxStore()
        store.ingest([_entrada()], origem=OrigemAchado.SCAN, tenant_id=TENANT)
        achado_id = store.listar()[0].id

        with pytest.raises(NotaObrigatoria):
            store.ack(achado_id, "")

    def test_ack_com_nota_so_espacos_levanta_nota_obrigatoria(self) -> None:
        store = InboxStore()
        store.ingest([_entrada()], origem=OrigemAchado.SCAN, tenant_id=TENANT)
        achado_id = store.listar()[0].id

        with pytest.raises(NotaObrigatoria):
            store.ack(achado_id, "   ")

    def test_defer_sem_nota_levanta_nota_obrigatoria(self) -> None:
        store = InboxStore()
        store.ingest([_entrada()], origem=OrigemAchado.SCAN, tenant_id=TENANT)
        achado_id = store.listar()[0].id

        with pytest.raises(NotaObrigatoria):
            store.defer(achado_id, "")

    def test_ack_de_id_inexistente_levanta_achado_desconhecido(self) -> None:
        store = InboxStore()
        with pytest.raises(AchadoInboxDesconhecido):
            store.ack("id-que-nao-existe", "nota valida")

    def test_defer_de_id_inexistente_levanta_achado_desconhecido(self) -> None:
        store = InboxStore()
        with pytest.raises(AchadoInboxDesconhecido):
            store.defer("id-que-nao-existe", "nota valida")

    def test_obter_de_id_inexistente_levanta_achado_desconhecido(self) -> None:
        store = InboxStore()
        with pytest.raises(AchadoInboxDesconhecido):
            store.obter("id-que-nao-existe")

    def test_achado_tratado_some_da_listagem_default(self) -> None:
        store = InboxStore()
        store.ingest([_entrada()], origem=OrigemAchado.SCAN, tenant_id=TENANT)
        achado_id = store.listar()[0].id
        store.ack(achado_id, "fix aplicado")

        assert store.listar() == []
        assert len(store.listar(apenas_novos=False)) == 1

    def test_nota_obrigatoria_nao_muda_estado_do_achado(self) -> None:
        """Falha de validacao nao pode deixar o achado num estado
        intermediario -- a excecao e levantada ANTES de qualquer UPDATE."""
        store = InboxStore()
        store.ingest([_entrada()], origem=OrigemAchado.SCAN, tenant_id=TENANT)
        achado_id = store.listar()[0].id

        with pytest.raises(NotaObrigatoria):
            store.ack(achado_id, "")

        assert store.obter(achado_id).status == StatusAchadoInbox.NOVO


class TestListarOrdenacao:
    def test_ordena_por_severidade_decrescente(self) -> None:
        store = InboxStore()
        store.ingest(
            [
                _entrada(chave="baixa-mas-alta-o-bastante", severidade=Criticidade.MEDIUM),
                _entrada(chave="critica", severidade=Criticidade.CRITICAL),
                _entrada(chave="alta", severidade=Criticidade.HIGH),
            ],
            origem=OrigemAchado.SCAN,
            tenant_id=TENANT,
        )

        achados = store.listar()
        severidades = [a.severidade for a in achados]
        assert severidades == [Criticidade.CRITICAL, Criticidade.HIGH, Criticidade.MEDIUM]

    def test_desempate_por_criado_em_crescente(self) -> None:
        store = InboxStore()
        t0 = datetime(2026, 1, 1, tzinfo=UTC)
        t1 = t0 + timedelta(hours=1)
        entrada_segundo = _entrada(chave="segundo", severidade=Criticidade.HIGH)
        entrada_primeiro = _entrada(chave="primeiro", severidade=Criticidade.HIGH)
        # 'segundo' criado em t1 primeiro; depois 'primeiro' entra na MESMA
        # ingestao que 'segundo' (retrato completo) para 'segundo' nao ser
        # auto-resolvido por "sumir" da segunda chamada.
        store.ingest([entrada_segundo], origem=OrigemAchado.SCAN, tenant_id=TENANT, agora_=t1)
        store.ingest(
            [entrada_segundo, entrada_primeiro],
            origem=OrigemAchado.SCAN,
            tenant_id=TENANT,
            agora_=t0,
        )

        achados = store.listar()
        assert [a.criado_em for a in achados] == [t0, t1]


class TestMapearSeveridadeAlerta:
    def test_info_vira_low(self) -> None:
        assert mapear_severidade_alerta(SeveridadeAlerta.INFO) == Criticidade.LOW

    def test_warning_vira_medium(self) -> None:
        assert mapear_severidade_alerta(SeveridadeAlerta.WARNING) == Criticidade.MEDIUM

    def test_critical_vira_critical(self) -> None:
        assert mapear_severidade_alerta(SeveridadeAlerta.CRITICAL) == Criticidade.CRITICAL


class TestPersistenciaReal:
    def test_sobrevive_a_reabrir_o_store_no_mesmo_arquivo(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "estado.db")

        store1 = InboxStore(db_path)
        store1.ingest([_entrada()], origem=OrigemAchado.SCAN, tenant_id=TENANT)
        store1.fechar()

        store2 = InboxStore(db_path)
        achados = store2.listar()
        assert len(achados) == 1

    def test_context_manager_fecha_a_conexao(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "estado.db")
        with InboxStore(db_path) as store:
            store.ingest([_entrada()], origem=OrigemAchado.SCAN, tenant_id=TENANT)
        assert len(InboxStore(db_path).listar()) == 1
