"""Testes do Governance Engine (Vol.VII Cap.27) — AT-27.1 a AT-27.3."""

from __future__ import annotations

import ast
import inspect

import pytest

from batman_os.foundation.types import AlertId, Evidence, HumanReviewRef
from batman_os.governance import governance_engine
from batman_os.governance.governance_engine import (
    AddendumRecord,
    AlertaDesconhecido,
    EvidenciaObrigatoriaParaAlerta,
    FonteAlerta,
    GovernanceAlert,
    GovernanceEngine,
    RevisaoHumanaObrigatoriaParaAnexo,
    SeveridadeAlerta,
    StatusAlerta,
    StatusAnexo,
    aceitar_anexo,
)


def _alerta(
    source: FonteAlerta = FonteAlerta.SLA_BREACH,
    severity: SeveridadeAlerta = SeveridadeAlerta.WARNING,
    evidence: list[Evidence] | None = None,
) -> GovernanceAlert:
    return GovernanceAlert(
        source=source,
        severity=severity,
        evidence=evidence if evidence is not None else [Evidence(origem="teste", evidencias=["x"])],
    )


class TestAT271EvidenciaObrigatoriaParaAlerta:
    def test_alerta_sem_evidencia_falha(self) -> None:
        engine = GovernanceEngine()
        with pytest.raises(EvidenciaObrigatoriaParaAlerta):
            engine.raise_alert(_alerta(evidence=[]))

    def test_alerta_com_evidencia_e_registrado(self) -> None:
        engine = GovernanceEngine()
        alerta = _alerta()
        engine.raise_alert(alerta)

        abertos = engine.get_open_alerts()
        assert len(abertos) == 1
        assert abertos[0].id == alerta.id

    def test_filtro_por_source_e_severity(self) -> None:
        engine = GovernanceEngine()
        engine.raise_alert(_alerta(source=FonteAlerta.SLA_BREACH, severity=SeveridadeAlerta.INFO))
        engine.raise_alert(
            _alerta(source=FonteAlerta.LLM_CIRCUIT_BREAKER, severity=SeveridadeAlerta.CRITICAL)
        )

        criticos = engine.get_open_alerts(severity=SeveridadeAlerta.CRITICAL)
        assert len(criticos) == 1
        assert criticos[0].source == FonteAlerta.LLM_CIRCUIT_BREAKER

    def test_acknowledge_e_resolve_transicionam_status(self) -> None:
        engine = GovernanceEngine()
        alerta = _alerta()
        engine.raise_alert(alerta)

        reconhecido = engine.acknowledge(alerta.id, by=HumanReviewRef("review-1"))
        assert reconhecido.status == StatusAlerta.ACKNOWLEDGED
        assert reconhecido.acknowledged_by == HumanReviewRef("review-1")
        assert reconhecido not in engine.get_open_alerts()

        resolvido = engine.resolve(alerta.id, resolution="SLA renegociado")
        assert resolvido.status == StatusAlerta.RESOLVED
        assert resolvido.resolution == "SLA renegociado"

    def test_operar_sobre_alerta_desconhecido_falha(self) -> None:
        engine = GovernanceEngine()
        with pytest.raises(AlertaDesconhecido):
            engine.acknowledge(AlertId("inexistente"), by=HumanReviewRef("review-1"))


class TestAT272AnexoNuncaAceitoSemHumanReview:
    def test_aceitar_sem_reviewed_by_falha(self) -> None:
        anexo = AddendumRecord(add_id="ADD-0002")
        with pytest.raises(RevisaoHumanaObrigatoriaParaAnexo):
            aceitar_anexo(anexo, reviewed_by=None)

    def test_aceitar_com_reviewed_by_funciona(self) -> None:
        anexo = AddendumRecord(add_id="ADD-0004")
        aceito = aceitar_anexo(anexo, reviewed_by=HumanReviewRef("review-autor"))

        assert aceito.status == StatusAnexo.ACCEPTED
        assert aceito.reviewed_by == HumanReviewRef("review-autor")

    def test_anexo_original_nao_e_mutado(self) -> None:
        anexo = AddendumRecord(add_id="ADD-0006")
        aceitar_anexo(anexo, reviewed_by=HumanReviewRef("review-autor"))

        assert anexo.status == StatusAnexo.PROPOSED
        assert anexo.reviewed_by is None


class TestAT273GovernanceEngineSemAutoridadeExecutivaDireta:
    def test_modulo_nunca_importa_do_kernel(self) -> None:
        """AT-27.3 — auditoria estática: nenhum caminho de código deste
        módulo pode importar `batman_os.kernel` (onde vivem as funções de
        mutação do Kernel: `transition`, `cancel`, etc. — ADR-0012)."""
        codigo_fonte = inspect.getsource(governance_engine)
        arvore = ast.parse(codigo_fonte)

        modulos_importados: list[str] = []
        for no in ast.walk(arvore):
            if isinstance(no, ast.Import):
                modulos_importados.extend(alias.name for alias in no.names)
            elif isinstance(no, ast.ImportFrom) and no.module:
                modulos_importados.append(no.module)

        violacoes = [m for m in modulos_importados if m.startswith("batman_os.kernel")]
        assert violacoes == []

    def test_governance_engine_nao_expoe_nenhum_metodo_de_mutacao_do_kernel(self) -> None:
        """Nenhum método público de `GovernanceEngine` tem nome que sugira
        mutação direta de Missão (`transition`, `cancel_mission`, etc.)."""
        nomes_proibidos = {"transition", "cancel_mission", "cancel", "create_mission"}
        metodos_publicos = {
            nome
            for nome, _ in inspect.getmembers(GovernanceEngine, predicate=inspect.isfunction)
            if not nome.startswith("_")
        }
        assert metodos_publicos.isdisjoint(nomes_proibidos)
