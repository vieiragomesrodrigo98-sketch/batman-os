"""Fila persistente de achados acionáveis ("inbox") — capacidade nova de
Governança (Anexo ao Vol.VII), sem capítulo próprio na especificação
(`docs/spec/` não menciona "inbox"; mesmo status de `alert_sinks.py`:
formalizável via Anexo/`StatusAnexo` quando a Governança decidir). Não
importa `batman_os.kernel` (ADR-0012 aplicada por analogia — este módulo só
CONSOME achados/alertas já prontos de scan/monitor, nunca decide nada do
Kernel).

Contexto (a função real que motivou este módulo): no cutover do Batman
legado (`radar-preditivo`, 2026-07-23) morreu o mecanismo mais valioso do
fluxo de governança daquele projeto — o INBOX da patrulha, uma fila
persistente de achados onde cada item era FORÇADO a ter um destino (fix /
virar regra / deferimento explícito, nunca "ignorado até sumir"). Hoje
`batman scan`/`batman monitor` alertam (terminal, Discord), mas um alerta
ignorado evapora: sem fila, sem cobrança. Este módulo fecha essa lacuna —
doutrina do projeto: "patrulha não é telemetria; rodar por rodar não
existe" e "zero débito: só o humano defere".

Reusa a MESMA infraestrutura de persistência que `EventBus`/
`OperationalMemory` já usam (Milestone 5 do roadmap de plataforma) — o
SQLite de `--db` (default `.batman-os/estado.db`) — em vez de inventar
armazenamento paralelo: só uma tabela nova (`inbox_achados`), criada de
forma idempotente no `__init__` de `InboxStore` (mesmo padrão de
`EventBus`/`OperationalMemory`: `CREATE TABLE IF NOT EXISTS` no boot; este
repositório ainda não tem um módulo de migração dedicado — ver nota em
`OperationalMemory`).

Camadas (Vol.VIII Cap.32, seção 32.3): este módulo vive em `governance/` e
NUNCA importa de `cli/` — os tipos concretos que cada origem produz
(`AchadoScan` em `cli/scan_command.py`, `GovernanceAlert` em
`governance/governance_engine.py`) são traduzidos para o formato genérico
`AchadoInboxEntrada` pelo lado que já os conhece: os adaptadores vivem em
`cli/scan_command.py::achados_para_inbox` e
`cli/monitor_command.py::alertas_para_inbox`.
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel

from batman_os.foundation.types import Criticidade, TenantId, Timestamp, agora
from batman_os.governance.governance_engine import SeveridadeAlerta


class OrigemAchado(StrEnum):
    """De onde veio o achado que entrou no inbox."""

    SCAN = "scan"
    MONITOR = "monitor"
    OBSERVE = "observe"  # reservado -- sem wiring de CLI ainda (`cli/observe_command.py`)


class StatusAchadoInbox(StrEnum):
    """NOVO/TRATADO/DEFERIDO são decisões humanas (via `batman inbox
    ack`/`defer`); RESOLVIDO é automático (ver `InboxStore.ingest`)."""

    NOVO = "novo"
    TRATADO = "tratado"
    DEFERIDO = "deferido"
    RESOLVIDO = "resolvido"


_RANK_SEVERIDADE: dict[Criticidade, int] = {
    Criticidade.LOW: 0,
    Criticidade.MEDIUM: 1,
    Criticidade.HIGH: 2,
    Criticidade.CRITICAL: 3,
}

LIMIAR_PADRAO = Criticidade.MEDIUM


def mapear_severidade_alerta(severidade: SeveridadeAlerta) -> Criticidade:
    """Traduz o vocabulário de 3 níveis do `GovernanceAlert`
    (`SeveridadeAlerta`: info/warning/critical) para o vocabulário de 4
    níveis do inbox (`Criticidade`, reusado de `foundation/types.py` — já
    compartilhado por `MissionTypeDefinition` e outros, mesmo espírito de
    reuso de tipo do resto do repo, em vez de inventar um enum de
    severidade paralelo). Mapeamento: INFO->LOW, WARNING->MEDIUM,
    CRITICAL->CRITICAL — `Criticidade.HIGH` nunca é produzida a partir de
    um `GovernanceAlert` (o vocabulário de origem não tem esse nível
    intermediário); escolha documentada, não um gap."""
    return {
        SeveridadeAlerta.INFO: Criticidade.LOW,
        SeveridadeAlerta.WARNING: Criticidade.MEDIUM,
        SeveridadeAlerta.CRITICAL: Criticidade.CRITICAL,
    }[severidade]


class AchadoInboxEntrada(BaseModel):
    """Formato genérico de ingestão — o que `InboxStore.ingest` consome,
    independente da origem concreta (scan/monitor/observe).

    `chave_dominio` é a identidade de domínio do achado DENTRO da origem
    (ex.: `f"{codigo}|{arquivo}|{chave}"` para scan, `f"{source}|{alvo}"`
    para monitor) — NUNCA inclui severidade/título/detalhe: esses campos
    podem mudar entre execuções (refresh de conteúdo) sem que o achado
    vire uma linha nova na fila."""

    chave_dominio: str
    severidade: Criticidade
    titulo: str
    detalhe: str


class AchadoInbox(BaseModel):
    """Uma linha da fila — o que `InboxStore.listar`/`obter` devolvem."""

    id: str
    origem: OrigemAchado
    tenant_id: TenantId
    severidade: Criticidade
    titulo: str
    detalhe: str
    criado_em: Timestamp
    atualizado_em: Timestamp
    status: StatusAchadoInbox = StatusAchadoInbox.NOVO
    tratado_em: Timestamp | None = None
    nota: str | None = None


class ResumoIngestao(BaseModel):
    """Retorno de `InboxStore.ingest` — contagem por efeito, para o
    wiring de CLI (`batman scan`/`batman monitor`) imprimir sem
    reconsultar o banco."""

    novos: int = 0
    atualizados: int = 0
    resolvidos_automaticamente: int = 0


class NotaObrigatoria(Exception):
    """`ack`/`defer` sem `nota` preenchida (mesma disciplina de
    `RationaleObrigatorio` em `governance/human_review.py`, AT-28.1) — uma
    decisão de triagem sem justificativa é epistemicamente equivalente a
    nenhuma decisão ter ocorrido (doutrina do projeto: "zero débito: só o
    humano defere" — e o humano precisa dizer POR QUÊ)."""


class AchadoInboxDesconhecido(Exception):
    """`ack`/`defer`/`obter` chamado com um id que não existe na fila."""


def calcular_id_estavel(origem: OrigemAchado, tenant_id: TenantId, chave_dominio: str) -> str:
    """Hash determinístico (sem componente aleatório/tempo) — a mesma
    tripla (origem, tenant, chave_dominio) SEMPRE produz o mesmo id, em
    qualquer execução. É o que torna `ingest` idempotente: um re-scan do
    MESMO achado faz upsert pelo id, nunca duplica linha."""
    bruto = f"{origem.value}|{tenant_id}|{chave_dominio}"
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()[:16]


def _serializar_ts(momento: Timestamp | None) -> str | None:
    return momento.isoformat() if momento is not None else None


class InboxStore:
    """Fila persistente. `db_path` — mesmo parâmetro/convenção de
    `EventBus`/`OperationalMemory` (Milestone 5): `":memory:"` (default)
    para testes efêmeros; um caminho real (CLI: `--db`, default
    `.batman-os/estado.db`) sobrevive entre execuções."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(db_path)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS inbox_achados ("
            "id TEXT PRIMARY KEY, "
            "origem TEXT NOT NULL, "
            "tenant_id TEXT NOT NULL, "
            "severidade TEXT NOT NULL, "
            "titulo TEXT NOT NULL, "
            "detalhe TEXT NOT NULL, "
            "criado_em TEXT NOT NULL, "
            "atualizado_em TEXT NOT NULL, "
            "status TEXT NOT NULL, "
            "tratado_em TEXT, "
            "nota TEXT"
            ")"
        )
        if db_path != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.commit()

    def fechar(self) -> None:
        self._conn.close()

    def __enter__(self) -> InboxStore:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.fechar()

    # -- ingestão -----------------------------------------------------------

    def ingest(
        self,
        entradas: list[AchadoInboxEntrada],
        *,
        origem: OrigemAchado,
        tenant_id: TenantId,
        limiar: Criticidade = LIMIAR_PADRAO,
        agora_: Timestamp | None = None,
    ) -> ResumoIngestao:
        """Upsert idempotente pelo id estável + auto-resolução por
        ausência (escolha documentada, ponto 1 do pacote).

        Cada chamada de `ingest` para um (origem, tenant_id) é tratada
        como o retrato COMPLETO e atual daquela origem: TODO achado em
        `entradas` (mesmo abaixo de `limiar`) conta como "detectado
        agora" para fins de auto-resolução — só quem está ACIMA de
        `limiar` de fato entra/atualiza a fila (isola a decisão "isto é
        relevante o bastante pra fila" de "isto ainda existe", para uma
        mudança de `limiar` entre execuções nunca resolver
        automaticamente um achado que continua lá, só ficou abaixo do
        novo corte).

        Uma linha existente da MESMA (origem, tenant_id) que não aparece
        em `entradas` é considerada corrigida e marcada `RESOLVIDO`
        automaticamente (nunca apagada — auditoria completa preservada,
        no espírito append-only de `OperationalMemory`/`EventBus`). Se um
        achado `RESOLVIDO` REAPARECER num scan futuro (regressão), volta
        para `NOVO` (precisa de triagem de novo; `tratado_em` é limpo,
        `nota` é preservada como histórico). Achados `TRATADO`/`DEFERIDO`
        que continuam aparecendo têm só o conteúdo/timestamp atualizados
        — o STATUS de decisão humana nunca é sobrescrito por uma
        re-detecção."""
        momento = agora_ or agora()
        ids_detectados = {
            calcular_id_estavel(origem, tenant_id, entrada.chave_dominio) for entrada in entradas
        }
        relevantes = [
            entrada
            for entrada in entradas
            if _RANK_SEVERIDADE[entrada.severidade] >= _RANK_SEVERIDADE[limiar]
        ]

        novos = 0
        atualizados = 0
        for entrada in relevantes:
            achado_id = calcular_id_estavel(origem, tenant_id, entrada.chave_dominio)
            existente = self._buscar_por_id(achado_id)
            if existente is None:
                self._inserir(achado_id, origem, tenant_id, entrada, momento)
                novos += 1
            else:
                self._atualizar_conteudo(achado_id, entrada, existente, momento)
                atualizados += 1

        resolvidos = self._resolver_ausentes(origem, tenant_id, ids_detectados, momento)
        return ResumoIngestao(
            novos=novos, atualizados=atualizados, resolvidos_automaticamente=resolvidos
        )

    def _inserir(
        self,
        achado_id: str,
        origem: OrigemAchado,
        tenant_id: TenantId,
        entrada: AchadoInboxEntrada,
        momento: Timestamp,
    ) -> None:
        self._conn.execute(
            "INSERT INTO inbox_achados "
            "(id, origem, tenant_id, severidade, titulo, detalhe, criado_em, atualizado_em, "
            "status, tratado_em, nota) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                achado_id,
                origem.value,
                str(tenant_id),
                entrada.severidade.value,
                entrada.titulo,
                entrada.detalhe,
                momento.isoformat(),
                momento.isoformat(),
                StatusAchadoInbox.NOVO.value,
                None,
                None,
            ),
        )
        self._conn.commit()

    def _atualizar_conteudo(
        self,
        achado_id: str,
        entrada: AchadoInboxEntrada,
        existente: AchadoInbox,
        momento: Timestamp,
    ) -> None:
        novo_status = existente.status
        tratado_em = existente.tratado_em
        if existente.status == StatusAchadoInbox.RESOLVIDO:
            # Regressao: o achado sumiu (foi marcado RESOLVIDO) e voltou a
            # aparecer -- exige triagem de novo. `nota` humana anterior
            # (se houver) e preservada como historico, nao apagada.
            novo_status = StatusAchadoInbox.NOVO
            tratado_em = None
        self._conn.execute(
            "UPDATE inbox_achados SET severidade=?, titulo=?, detalhe=?, atualizado_em=?, "
            "status=?, tratado_em=? WHERE id=?",
            (
                entrada.severidade.value,
                entrada.titulo,
                entrada.detalhe,
                momento.isoformat(),
                novo_status.value,
                _serializar_ts(tratado_em),
                achado_id,
            ),
        )
        self._conn.commit()

    def _resolver_ausentes(
        self,
        origem: OrigemAchado,
        tenant_id: TenantId,
        ids_detectados: set[str],
        momento: Timestamp,
    ) -> int:
        cursor = self._conn.execute(
            "SELECT id FROM inbox_achados WHERE origem=? AND tenant_id=? AND status != ?",
            (origem.value, str(tenant_id), StatusAchadoInbox.RESOLVIDO.value),
        )
        ausentes = [row[0] for row in cursor.fetchall() if row[0] not in ids_detectados]
        for achado_id in ausentes:
            self._conn.execute(
                "UPDATE inbox_achados SET status=?, atualizado_em=?, tratado_em=? WHERE id=?",
                (
                    StatusAchadoInbox.RESOLVIDO.value,
                    momento.isoformat(),
                    momento.isoformat(),
                    achado_id,
                ),
            )
        if ausentes:
            self._conn.commit()
        return len(ausentes)

    # -- consulta -------------------------------------------------------------

    def _buscar_por_id(self, achado_id: str) -> AchadoInbox | None:
        cursor = self._conn.execute(
            "SELECT id, origem, tenant_id, severidade, titulo, detalhe, criado_em, "
            "atualizado_em, status, tratado_em, nota FROM inbox_achados WHERE id=?",
            (achado_id,),
        )
        linha = cursor.fetchone()
        return _achado_da_linha(linha) if linha is not None else None

    def obter(self, achado_id: str) -> AchadoInbox:
        achado = self._buscar_por_id(achado_id)
        if achado is None:
            raise AchadoInboxDesconhecido(f"id '{achado_id}' nao existe no inbox")
        return achado

    def listar(
        self, *, apenas_novos: bool = True, tenant_id: TenantId | None = None
    ) -> list[AchadoInbox]:
        """`apenas_novos=True` (default do `batman inbox list`) só devolve
        `StatusAchadoInbox.NOVO`; `apenas_novos=False` (`--all`) devolve
        tudo, qualquer status. `tenant_id` ausente = cross-tenant por
        design (mesmo padrão de `OperationalMemory.all_records()` — quem
        opera a fila plausivelmente precisa ver achados de todos os
        tenants; filtro disponível para quem quiser escopar).

        Ordenação: severidade decrescente (mais grave primeiro), depois
        `criado_em` crescente (o mais antigo de cada severidade primeiro
        — evita que um achado fique soterrado para sempre)."""
        query = (
            "SELECT id, origem, tenant_id, severidade, titulo, detalhe, criado_em, "
            "atualizado_em, status, tratado_em, nota FROM inbox_achados WHERE 1=1"
        )
        parametros: list[str] = []
        if apenas_novos:
            query += " AND status=?"
            parametros.append(StatusAchadoInbox.NOVO.value)
        if tenant_id is not None:
            query += " AND tenant_id=?"
            parametros.append(str(tenant_id))
        cursor = self._conn.execute(query, parametros)
        achados = [_achado_da_linha(linha) for linha in cursor.fetchall()]
        achados.sort(key=lambda a: (-_RANK_SEVERIDADE[a.severidade], a.criado_em))
        return achados

    # -- decisão humana -------------------------------------------------------

    def ack(self, achado_id: str, nota: str, *, agora_: Timestamp | None = None) -> AchadoInbox:
        """Marca `TRATADO` — a correção foi feita (fix)."""
        return self._transicionar(achado_id, StatusAchadoInbox.TRATADO, nota, agora_)

    def defer(self, achado_id: str, nota: str, *, agora_: Timestamp | None = None) -> AchadoInbox:
        """Marca `DEFERIDO` — decisão humana explícita de não tratar
        agora (doutrina "zero débito: só o humano defere", nunca
        automático)."""
        return self._transicionar(achado_id, StatusAchadoInbox.DEFERIDO, nota, agora_)

    def _transicionar(
        self,
        achado_id: str,
        novo_status: StatusAchadoInbox,
        nota: str,
        agora_: Timestamp | None,
    ) -> AchadoInbox:
        if not nota.strip():
            raise NotaObrigatoria(
                f"transicao para '{novo_status.value}' do achado '{achado_id}' exige nota "
                "preenchida (AT-28.1-like: decisao sem justificativa == nenhuma decisao)"
            )
        self.obter(achado_id)  # levanta AchadoInboxDesconhecido se nao existir
        momento = agora_ or agora()
        self._conn.execute(
            "UPDATE inbox_achados SET status=?, tratado_em=?, nota=?, atualizado_em=? WHERE id=?",
            (novo_status.value, momento.isoformat(), nota, momento.isoformat(), achado_id),
        )
        self._conn.commit()
        return self.obter(achado_id)


def _achado_da_linha(linha: tuple[object, ...]) -> AchadoInbox:
    (
        id_,
        origem,
        tenant_id,
        severidade,
        titulo,
        detalhe,
        criado_em,
        atualizado_em,
        status,
        tratado_em,
        nota,
    ) = linha
    return AchadoInbox(
        id=str(id_),
        origem=OrigemAchado(str(origem)),
        tenant_id=TenantId(str(tenant_id)),
        severidade=Criticidade(str(severidade)),
        titulo=str(titulo),
        detalhe=str(detalhe),
        criado_em=_desserializar_ts(str(criado_em)),
        atualizado_em=_desserializar_ts(str(atualizado_em)),
        status=StatusAchadoInbox(str(status)),
        tratado_em=_desserializar_ts(str(tratado_em)) if tratado_em is not None else None,
        nota=str(nota) if nota is not None else None,
    )


def _desserializar_ts(bruto: str) -> Timestamp:
    return datetime.fromisoformat(bruto)
