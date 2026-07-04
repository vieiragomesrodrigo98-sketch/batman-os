"""Testes do Observability Engine (Vol.VII Cap.30) — AT-30.1 a AT-30.3."""

from __future__ import annotations

import ast
import inspect
from datetime import timedelta

from batman_os.foundation.types import agora
from batman_os.governance import observability_engine
from batman_os.governance.governance_engine import (
    FonteAlerta,
    GovernanceEngine,
    SeveridadeAlerta,
    StatusAlerta,
)
from batman_os.governance.observability_engine import (
    AlertRule,
    AlertRuleId,
    MetricId,
    ModeloDeAlerta,
    NomeDoPainel,
    ObservabilityEngine,
    PontoDeSerie,
    construir_serie,
)


class TestAT301MetricaReprodutivelIndependentemente:
    def test_mesma_lista_de_pontos_produz_a_mesma_serie(self) -> None:
        agora_ = agora()
        pontos = [
            PontoDeSerie(timestamp=agora_, value=0.1),
            PontoDeSerie(timestamp=agora_ + timedelta(hours=1), value=0.2),
        ]

        serie_1 = construir_serie(MetricId("m-1"), pontos, janela_agregacao=timedelta(hours=1))
        serie_2 = construir_serie(MetricId("m-1"), pontos, janela_agregacao=timedelta(hours=1))

        assert serie_1.points == serie_2.points
        assert serie_1.metric_id == serie_2.metric_id

    def test_serie_sempre_carrega_metadado_de_janela_e_reconciliacao(self) -> None:
        """Secao 30.6 — honestidade epistemica estrutural, nao opcional."""
        serie = construir_serie(MetricId("m-1"), [], janela_agregacao=timedelta(hours=1))

        assert serie.janela_agregacao == timedelta(hours=1)
        assert serie.reconciliado_em is not None

    def test_pontos_sao_ordenados_por_tempo(self) -> None:
        agora_ = agora()
        pontos_fora_de_ordem = [
            PontoDeSerie(timestamp=agora_ + timedelta(hours=2), value=0.3),
            PontoDeSerie(timestamp=agora_, value=0.1),
            PontoDeSerie(timestamp=agora_ + timedelta(hours=1), value=0.2),
        ]

        serie = construir_serie(MetricId("m-1"), pontos_fora_de_ordem, timedelta(hours=1))

        assert [p.value for p in serie.points] == [0.1, 0.2, 0.3]

    def test_get_metric_retorna_serie_registrada(self) -> None:
        engine = ObservabilityEngine(GovernanceEngine())
        serie = construir_serie(MetricId("m-1"), [], timedelta(hours=1))
        engine.registrar_serie(serie)

        assert engine.get_metric(MetricId("m-1")) is serie
        assert engine.get_metric(MetricId("inexistente")) is None

    def test_get_dashboard_agrupa_por_painel(self) -> None:
        engine = ObservabilityEngine(GovernanceEngine())
        engine.registrar_serie(
            construir_serie(MetricId("cognitive-debt-global"), [], timedelta(hours=1))
        )
        engine.registrar_serie(
            construir_serie(MetricId("backlog-human-review"), [], timedelta(hours=1))
        )

        painel = engine.get_dashboard(NomeDoPainel.COGNITIVE_DEBT)
        assert set(painel.keys()) == {MetricId("cognitive-debt-global")}


class TestAT302TrendWorseningDisparaSemViolarLimiarIsolado:
    def _regra_trend(self, metric_id: MetricId) -> AlertRule:
        return AlertRule(
            id=AlertRuleId("regra-1"),
            metric_id=metric_id,
            condition="trend-worsening",
            threshold=999.0,  # limiar absoluto NUNCA violado por nenhum ponto isolado
            window=timedelta(days=7),
            raises_alert_with=ModeloDeAlerta(
                source=FonteAlerta.RULE_DRIFT, severity=SeveridadeAlerta.WARNING
            ),
        )

    def test_piora_sustentada_dispara_alerta(self) -> None:
        agora_ = agora()
        governance = GovernanceEngine()
        engine = ObservabilityEngine(governance)
        pontos = [
            PontoDeSerie(timestamp=agora_ - timedelta(days=2), value=0.1),
            PontoDeSerie(timestamp=agora_ - timedelta(days=1), value=0.2),
            PontoDeSerie(timestamp=agora_, value=0.3),
        ]
        engine.registrar_serie(construir_serie(MetricId("m-1"), pontos, timedelta(hours=1)))
        engine.register_alert_rule(self._regra_trend(MetricId("m-1")))

        disparados = engine.avaliar_regras(agora_=agora_)

        assert len(disparados) == 1
        assert governance.get_open_alerts()[0].source == FonteAlerta.RULE_DRIFT

    def test_serie_estavel_nao_dispara(self) -> None:
        agora_ = agora()
        engine = ObservabilityEngine(GovernanceEngine())
        pontos = [
            PontoDeSerie(timestamp=agora_ - timedelta(days=2), value=0.2),
            PontoDeSerie(timestamp=agora_ - timedelta(days=1), value=0.2),
            PontoDeSerie(timestamp=agora_, value=0.2),
        ]
        engine.registrar_serie(construir_serie(MetricId("m-1"), pontos, timedelta(hours=1)))
        engine.register_alert_rule(self._regra_trend(MetricId("m-1")))

        assert engine.avaliar_regras(agora_=agora_) == []

    def test_melhora_nao_dispara_trend_worsening(self) -> None:
        agora_ = agora()
        engine = ObservabilityEngine(GovernanceEngine())
        pontos = [
            PontoDeSerie(timestamp=agora_ - timedelta(days=2), value=0.3),
            PontoDeSerie(timestamp=agora_ - timedelta(days=1), value=0.2),
            PontoDeSerie(timestamp=agora_, value=0.1),
        ]
        engine.registrar_serie(construir_serie(MetricId("m-1"), pontos, timedelta(hours=1)))
        engine.register_alert_rule(self._regra_trend(MetricId("m-1")))

        assert engine.avaliar_regras(agora_=agora_) == []

    def test_above_ainda_funciona_normalmente(self) -> None:
        agora_ = agora()
        governance = GovernanceEngine()
        engine = ObservabilityEngine(governance)
        engine.registrar_serie(
            construir_serie(
                MetricId("m-1"), [PontoDeSerie(timestamp=agora_, value=0.9)], timedelta(hours=1)
            )
        )
        engine.register_alert_rule(
            AlertRule(
                id=AlertRuleId("regra-above"),
                metric_id=MetricId("m-1"),
                condition="above",
                threshold=0.5,
                window=timedelta(days=1),
                raises_alert_with=ModeloDeAlerta(
                    source=FonteAlerta.LLM_CIRCUIT_BREAKER, severity=SeveridadeAlerta.CRITICAL
                ),
            )
        )

        disparados = engine.avaliar_regras(agora_=agora_)
        assert len(disparados) == 1
        assert disparados[0].status == StatusAlerta.OPEN


class TestAT303IndisponibilidadeNuncaBloqueiaKernel:
    def test_modulo_nunca_importa_do_kernel(self) -> None:
        """AT-30.3 — mesma auditoria estática do Cap.27 (AT-27.3): se o
        Kernel nunca importa/depende deste módulo, sua indisponibilidade
        estruturalmente não pode bloquear nenhuma missão em andamento."""
        codigo_fonte = inspect.getsource(observability_engine)
        arvore = ast.parse(codigo_fonte)

        modulos_importados: list[str] = []
        for no in ast.walk(arvore):
            if isinstance(no, ast.Import):
                modulos_importados.extend(alias.name for alias in no.names)
            elif isinstance(no, ast.ImportFrom) and no.module:
                modulos_importados.append(no.module)

        violacoes = [m for m in modulos_importados if m.startswith("batman_os.kernel")]
        assert violacoes == []
