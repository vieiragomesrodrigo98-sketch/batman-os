"""Vol.IX Cap.34 — orquestrador real do "scan estático".

Migra `python -m Batman.scan.runner` (o motor legado) para o caminho real
Mission Runtime -> Planning Engine -> Decision Engine -> Workflow Engine ->
Execution Engine -> Operator -> Capability certificada, uma Missão por
(arquivo, regra) de todos os lotes já migrados
(`capabilities/rules/lote_01.py`, `lote_02.py`, ...).

Nota de escala (aceita no Milestone 1, ver plano de migração): 1 Missão por
(arquivo, regra) é correto e honesto, mas caro em repositórios grandes
(potencialmente centenas/milhares de Missões). Extensão natural quando o
foco virar performance: uma Capability que aceita lote de arquivos numa
única invocação.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

from batman_os.capabilities.capability_contract import CapabilityImplementation, certificar
from batman_os.capabilities.operator import (
    ExecutionContext,
    FilesystemAccess,
    NetworkPolicy,
    Operator,
    PermissionSet,
    ResourceLimits,
    SandboxPolicy,
    SideEffectScope,
)
from batman_os.capabilities.rules.a11y003_input_sem_label import EntradaA11y003, RegraA11y003Spec
from batman_os.capabilities.rules.a11y003_input_sem_label import (
    construir_implementacao as construir_implementacao_a11y003,
)
from batman_os.capabilities.rules.a11y003_loader import (
    SpecA11y003,
    carregar_especificacoes_a11y003,
)
from batman_os.capabilities.rules.arch003_loader import SpecArch003, carregar_especificacoes_arch003
from batman_os.capabilities.rules.arch003_pagina_orfa import EntradaArch003, RegraArch003Spec
from batman_os.capabilities.rules.arch003_pagina_orfa import (
    construir_implementacao as construir_implementacao_arch003,
)
from batman_os.capabilities.rules.ast_kwarg_ausente import (
    EntradaKwargAusente,
    RegraKwargAusenteSpec,
)
from batman_os.capabilities.rules.ast_kwarg_ausente import (
    construir_implementacao as construir_implementacao_kwarg_ausente,
)
from batman_os.capabilities.rules.ast_kwarg_ausente_loader import (
    SpecDeRegraKwargAusente,
    carregar_especificacoes_kwarg_ausente,
)
from batman_os.capabilities.rules.ast_padrao_ausente import (
    EntradaAst,
    RegraAstSpec,
)
from batman_os.capabilities.rules.ast_padrao_ausente import (
    construir_implementacao as construir_implementacao_ast,
)
from batman_os.capabilities.rules.ast_padrao_ausente_loader import (
    SpecDeRegraAst,
    carregar_especificacoes_ast,
)
from batman_os.capabilities.rules.ba004_loader import SpecBa004, carregar_especificacoes_ba004
from batman_os.capabilities.rules.ba004_logica_negocio_router import EntradaBa004, RegraBa004Spec
from batman_os.capabilities.rules.ba004_logica_negocio_router import (
    construir_implementacao as construir_implementacao_ba004,
)
from batman_os.capabilities.rules.ba005_divisao_sem_guarda import EntradaBa005, RegraBa005Spec
from batman_os.capabilities.rules.ba005_divisao_sem_guarda import (
    construir_implementacao as construir_implementacao_ba005,
)
from batman_os.capabilities.rules.ba005_loader import SpecBa005, carregar_especificacoes_ba005
from batman_os.capabilities.rules.be010_dependencia_nao_declarada import (
    EntradaBe010,
    RegraBe010Spec,
)
from batman_os.capabilities.rules.be010_dependencia_nao_declarada import (
    construir_implementacao as construir_implementacao_be010,
)
from batman_os.capabilities.rules.be010_loader import SpecBe010, carregar_especificacoes_be010
from batman_os.capabilities.rules.be013_http200_em_except import EntradaBe013, RegraBe013Spec
from batman_os.capabilities.rules.be013_http200_em_except import (
    construir_implementacao as construir_implementacao_be013,
)
from batman_os.capabilities.rules.be013_loader import SpecBe013, carregar_especificacoes_be013
from batman_os.capabilities.rules.cs003_except_pass import EntradaCs003, RegraCs003Spec
from batman_os.capabilities.rules.cs003_except_pass import (
    construir_implementacao as construir_implementacao_cs003,
)
from batman_os.capabilities.rules.cs003_loader import SpecCs003, carregar_especificacoes_cs003
from batman_os.capabilities.rules.cs005_erro_sem_request_id import EntradaCs005, RegraCs005Spec
from batman_os.capabilities.rules.cs005_erro_sem_request_id import (
    construir_implementacao as construir_implementacao_cs005,
)
from batman_os.capabilities.rules.cs005_loader import SpecCs005, carregar_especificacoes_cs005
from batman_os.capabilities.rules.de003_coluna_sem_migration import EntradaDe003, RegraDe003Spec
from batman_os.capabilities.rules.de003_coluna_sem_migration import (
    construir_implementacao as construir_implementacao_de003,
)
from batman_os.capabilities.rules.de003_loader import SpecDe003, carregar_especificacoes_de003
from batman_os.capabilities.rules.doc004_changelog_sem_versao import EntradaDoc004, RegraDoc004Spec
from batman_os.capabilities.rules.doc004_changelog_sem_versao import (
    construir_implementacao as construir_implementacao_doc004,
)
from batman_os.capabilities.rules.doc004_loader import SpecDoc004, carregar_especificacoes_doc004
from batman_os.capabilities.rules.execucao_comando_interpretada import (
    EntradaExecucaoComando,
    RegraExecucaoComandoSpec,
)
from batman_os.capabilities.rules.execucao_comando_interpretada import (
    construir_implementacao as construir_implementacao_execucao_comando,
)
from batman_os.capabilities.rules.execucao_comando_interpretada_loader import (
    SpecDeRegraExecucaoComando,
    carregar_especificacoes_execucao_comando,
)
from batman_os.capabilities.rules.fe001_export_duplicado import EntradaFe001, RegraFe001Spec
from batman_os.capabilities.rules.fe001_export_duplicado import (
    construir_implementacao as construir_implementacao_fe001,
)
from batman_os.capabilities.rules.fe001_loader import SpecFe001, carregar_especificacoes_fe001
from batman_os.capabilities.rules.feapi_loader import SpecFeApi, carregar_especificacoes_feapi
from batman_os.capabilities.rules.feapi_rota_sem_frontend import EntradaFeApi, RegraFeApiSpec
from batman_os.capabilities.rules.feapi_rota_sem_frontend import (
    construir_implementacao as construir_implementacao_feapi,
)
from batman_os.capabilities.rules.fin005_backtest_sem_oos import EntradaFin005, RegraFin005Spec
from batman_os.capabilities.rules.fin005_backtest_sem_oos import (
    construir_implementacao as construir_implementacao_fin005,
)
from batman_os.capabilities.rules.fin005_loader import SpecFin005, carregar_especificacoes_fin005
from batman_os.capabilities.rules.git_comando_interpretado import (
    EntradaGitInterpretado,
    RegraComparacaoNumericaSpec,
)
from batman_os.capabilities.rules.git_comando_interpretado import (
    construir_implementacao as construir_implementacao_git,
)
from batman_os.capabilities.rules.git_comando_interpretado_loader import (
    SpecDeRegraGitInterpretado,
    carregar_especificacoes_git_interpretado,
)
from batman_os.capabilities.rules.govdebt001_finding_sem_decisao import (
    EntradaGovdebt001,
    RegraGovdebt001Spec,
)
from batman_os.capabilities.rules.govdebt001_finding_sem_decisao import (
    construir_implementacao as construir_implementacao_govdebt001,
)
from batman_os.capabilities.rules.govdebt001_loader import (
    SpecGovdebt001,
    carregar_especificacoes_govdebt001,
)
from batman_os.capabilities.rules.janela_contexto_regex import EntradaJanela, RegraJanelaSpec
from batman_os.capabilities.rules.janela_contexto_regex import (
    construir_implementacao as construir_implementacao_janela,
)
from batman_os.capabilities.rules.janela_contexto_regex_loader import (
    SpecDeRegraJanela,
    carregar_especificacoes_janela,
)
from batman_os.capabilities.rules.lote_01 import SpecDeRegra, carregar_lote_01
from batman_os.capabilities.rules.lote_02 import carregar_lote_02
from batman_os.capabilities.rules.lote_03 import carregar_lote_03
from batman_os.capabilities.rules.metrica_com_limiar import EntradaMetrica, RegraMetricaSpec
from batman_os.capabilities.rules.metrica_com_limiar import (
    construir_implementacao as construir_implementacao_metrica,
)
from batman_os.capabilities.rules.metrica_com_limiar_loader import (
    SpecDeRegraMetrica,
    carregar_especificacoes_metrica,
)
from batman_os.capabilities.rules.ora004_loader import SpecOra004, carregar_especificacoes_ora004
from batman_os.capabilities.rules.ora004_status_typo import EntradaOra004, RegraOra004Spec
from batman_os.capabilities.rules.ora004_status_typo import (
    construir_implementacao as construir_implementacao_ora004,
)
from batman_os.capabilities.rules.ora005_fallback_silencioso import EntradaOra005, RegraOra005Spec
from batman_os.capabilities.rules.ora005_fallback_silencioso import (
    construir_implementacao as construir_implementacao_ora005,
)
from batman_os.capabilities.rules.ora005_loader import SpecOra005, carregar_especificacoes_ora005
from batman_os.capabilities.rules.pd001_empty_state_sem_cta import EntradaPd001, RegraPd001Spec
from batman_os.capabilities.rules.pd001_empty_state_sem_cta import (
    construir_implementacao as construir_implementacao_pd001,
)
from batman_os.capabilities.rules.pd001_loader import SpecPd001, carregar_especificacoes_pd001
from batman_os.capabilities.rules.pd009_loader import SpecPd009, carregar_especificacoes_pd009
from batman_os.capabilities.rules.pd009_rota_nao_descobrivel import EntradaPd009, RegraPd009Spec
from batman_os.capabilities.rules.pd009_rota_nao_descobrivel import (
    construir_implementacao as construir_implementacao_pd009,
)
from batman_os.capabilities.rules.pd010_loader import SpecPd010, carregar_especificacoes_pd010
from batman_os.capabilities.rules.pd010_simulador_sem_piso import EntradaPd010, RegraPd010Spec
from batman_os.capabilities.rules.pd010_simulador_sem_piso import (
    construir_implementacao as construir_implementacao_pd010,
)
from batman_os.capabilities.rules.pd011_diversificacao_nao_comunicada import (
    EntradaPd011,
    RegraPd011Spec,
)
from batman_os.capabilities.rules.pd011_diversificacao_nao_comunicada import (
    construir_implementacao as construir_implementacao_pd011,
)
from batman_os.capabilities.rules.pd011_loader import SpecPd011, carregar_especificacoes_pd011
from batman_os.capabilities.rules.qaauto001_loader import (
    SpecQaAuto001,
    carregar_especificacoes_qaauto001,
)
from batman_os.capabilities.rules.qaauto001_router_sem_teste import (
    EntradaQaAuto001,
    RegraQaAuto001Spec,
)
from batman_os.capabilities.rules.qaauto001_router_sem_teste import (
    construir_implementacao as construir_implementacao_qaauto001,
)
from batman_os.capabilities.rules.qaauto003_loader import (
    SpecQaAuto003,
    carregar_especificacoes_qaauto003,
)
from batman_os.capabilities.rules.qaauto003_smoke_specs_ausentes import (
    EntradaQaAuto003,
    RegraQaAuto003Spec,
)
from batman_os.capabilities.rules.qaauto003_smoke_specs_ausentes import (
    construir_implementacao as construir_implementacao_qaauto003,
)
from batman_os.capabilities.rules.regex_agregado_multi_arquivo import (
    EntradaAgregada,
    RegraAgregadaSpec,
)
from batman_os.capabilities.rules.regex_agregado_multi_arquivo import (
    construir_implementacao as construir_implementacao_agregada,
)
from batman_os.capabilities.rules.regex_agregado_multi_arquivo_loader import (
    SpecDeRegraAgregada,
    carregar_especificacoes_agregadas,
)
from batman_os.capabilities.rules.regex_sobre_conteudo import EntradaRegexArquivo
from batman_os.capabilities.rules.regex_sobre_conteudo import (
    construir_implementacao as construir_implementacao_regex,
)
from batman_os.capabilities.rules.rev006_loader import SpecRev006, carregar_especificacoes_rev006
from batman_os.capabilities.rules.rev006_variavel_nome_curto import EntradaRev006, RegraRev006Spec
from batman_os.capabilities.rules.rev006_variavel_nome_curto import (
    construir_implementacao as construir_implementacao_rev006,
)
from batman_os.capabilities.rules.sec005_fstring_sql import EntradaSec005, RegraSec005Spec
from batman_os.capabilities.rules.sec005_fstring_sql import (
    construir_implementacao as construir_implementacao_sec005,
)
from batman_os.capabilities.rules.sec005_loader import SpecSec005, carregar_especificacoes_sec005
from batman_os.capabilities.rules.sec007_ddl_no_import import EntradaSec007, RegraSec007Spec
from batman_os.capabilities.rules.sec007_ddl_no_import import (
    construir_implementacao as construir_implementacao_sec007,
)
from batman_os.capabilities.rules.sec007_loader import SpecSec007, carregar_especificacoes_sec007
from batman_os.capabilities.rules.sec008_loader import SpecSec008, carregar_especificacoes_sec008
from batman_os.capabilities.rules.sec008_role_sem_super_admin import (
    EntradaSec008,
    RegraSec008Spec,
)
from batman_os.capabilities.rules.sec008_role_sem_super_admin import (
    construir_implementacao as construir_implementacao_sec008,
)
from batman_os.capabilities.rules.sec009_admin_role_script import EntradaSec009, RegraSec009Spec
from batman_os.capabilities.rules.sec009_admin_role_script import (
    construir_implementacao as construir_implementacao_sec009,
)
from batman_os.capabilities.rules.sec009_loader import SpecSec009, carregar_especificacoes_sec009
from batman_os.capabilities.rules.sre006_loader import SpecSre006, carregar_especificacoes_sre006
from batman_os.capabilities.rules.sre006_timeout_ausente import EntradaSre006, RegraSre006Spec
from batman_os.capabilities.rules.sre006_timeout_ausente import (
    construir_implementacao as construir_implementacao_sre006,
)
from batman_os.capabilities.rules.sup001_excecao_silenciada import EntradaSup001, RegraSup001Spec
from batman_os.capabilities.rules.sup001_excecao_silenciada import (
    construir_implementacao as construir_implementacao_sup001,
)
from batman_os.capabilities.rules.sup001_loader import SpecSup001, carregar_especificacoes_sup001
from batman_os.capabilities.rules.sweep001_cadencia_quebrada import (
    EntradaSweep001,
    RegraSweep001Spec,
)
from batman_os.capabilities.rules.sweep001_cadencia_quebrada import (
    construir_implementacao as construir_implementacao_sweep001,
)
from batman_os.capabilities.rules.sweep001_loader import (
    SpecSweep001,
    carregar_especificacoes_sweep001,
)
from batman_os.capabilities.rules.toml_dependencias import (
    EntradaDependencias,
    RegraDependenciasSpec,
)
from batman_os.capabilities.rules.toml_dependencias import (
    construir_implementacao as construir_implementacao_dependencias,
)
from batman_os.capabilities.rules.toml_dependencias_loader import (
    SpecDeRegraDependencias,
    carregar_especificacoes_dependencias,
)
from batman_os.cli.descoberta_arquivos import (
    entradas_a11y003_para_regra,
    entradas_agregadas_para_regra,
    entradas_arch003_para_regra,
    entradas_ast_para_regra,
    entradas_ba004_para_regra,
    entradas_ba005_para_regra,
    entradas_be010_para_regra,
    entradas_be013_para_regra,
    entradas_cs003_para_regra,
    entradas_cs005_para_regra,
    entradas_de003_para_regra,
    entradas_dependencias_para_regra,
    entradas_doc004_para_regra,
    entradas_execucao_comando_para_regra,
    entradas_fe001_para_regra,
    entradas_feapi_para_regra,
    entradas_fin005_para_regra,
    entradas_git_interpretado_para_regra,
    entradas_govdebt001_para_regra,
    entradas_janela_para_regra,
    entradas_kwarg_ausente_para_regra,
    entradas_metrica_para_regra,
    entradas_ora004_para_regra,
    entradas_ora005_para_regra,
    entradas_para_regra,
    entradas_pd001_para_regra,
    entradas_pd009_para_regra,
    entradas_pd010_para_regra,
    entradas_pd011_para_regra,
    entradas_qaauto001_para_regra,
    entradas_qaauto003_para_regra,
    entradas_rev006_para_regra,
    entradas_sec005_para_regra,
    entradas_sec007_para_regra,
    entradas_sec008_para_regra,
    entradas_sec009_para_regra,
    entradas_sre006_para_regra,
    entradas_sup001_para_regra,
    entradas_sweep001_para_regra,
)
from batman_os.foundation.types import (
    CapabilityId,
    Criticidade,
    EscalationPolicy,
    MissionId,
    MissionTypeId,
    OperatorId,
    OperatorRef,
    Reversibilidade,
    StepId,
    TenantId,
    agora,
)
from batman_os.kernel.decision_engine import DecisionEngine, RespostaLlmCandidata
from batman_os.kernel.event_bus import EventBus
from batman_os.kernel.mission_runtime import (
    MissionEventType,
    MissionIntent,
    MissionRuntime,
)
from batman_os.kernel.planning_engine import DecisionPoint, plan
from batman_os.kernel.workflow_engine import WorkflowEngine
from batman_os.orchestration.implementation_registry import ExecutorViaImplementacoes
from batman_os.orchestration.operator_bridge import OperadorExecutavelAdapter
from batman_os.orchestration.schema_validators import (
    ValidadorContratoSempreAprova,
    ValidadorSchemaEstrutural,
)
from batman_os.orchestration.step_invoker import InvocadorDeStepPadrao, TabelaDeEntradasPorStep
from batman_os.runtime.capability_engine import CapabilityDefinition, CapabilityRegistry
from batman_os.runtime.execution_engine import ExecutionEngine
from batman_os.workflow.missions import MissionTypeDefinition, MissionTypeRegistry

TIPO_MISSAO = MissionTypeId("scan-estatico")
TENANT_PADRAO = TenantId("local")


@dataclass
class AchadoScan:
    """Espelha `capabilities.rules.regex_sobre_conteudo.Achado` — a saída
    que o operador vê no terminal."""

    codigo: str
    agente: str
    severidade: str
    categoria: str
    titulo: str
    descricao: str
    causa: str
    remediacao: str
    arquivo: str
    chave: str = ""
    fingerprint: str = ""


@dataclass
class ResultadoScan:
    achados: list[AchadoScan] = field(default_factory=list)

    def contagem_por_severidade(self) -> dict[str, int]:
        contagem: dict[str, int] = {}
        for achado in self.achados:
            contagem[achado.severidade] = contagem.get(achado.severidade, 0) + 1
        return contagem


class _SemConhecimentoAinda:
    """Vol.II Cap.8 — nenhuma regra migrada do Learning Engine (Vol.VI)
    alimenta o Decision Engine ainda para este fluxo; irrelevante na
    prática, já que uma regra determinística sem ambiguidade nunca produz
    um `DecisionPoint` na composição via grafo (Cap.7)."""

    def consultar(self, ponto: DecisionPoint) -> None:
        del ponto
        return None


class _LlmNuncaChamadoNesteFluxo:
    def consultar(self, ponto: DecisionPoint) -> RespostaLlmCandidata:
        del ponto
        raise AssertionError("scan estatico nunca escala para LLM - regra deterministica")


class _ValidadorSempreAprova:
    def validar(self, ponto: DecisionPoint, resposta: object) -> bool:
        del ponto, resposta
        return True


def _registro_tipos() -> MissionTypeRegistry:
    registro = MissionTypeRegistry()
    registro.register(
        MissionTypeDefinition(
            id=TIPO_MISSAO,
            criticality=Criticidade.LOW,
            default_sla=timedelta(hours=1),
            escalation_defaults=EscalationPolicy(
                confidence_threshold=0.8,
                preferred_escalation="human",
                max_llm_retries=1,
                reversibility=Reversibilidade.REVERSIVEL,
            ),
        )
    )
    return registro


def _certificar_com_idempotencia(
    implementacao: CapabilityImplementation, entrada_idempotencia: dict[str, object]
) -> CapabilityDefinition:
    contexto_certificacao = ExecutionContext(
        mission_id=MissionId("mission-certificacao"),
        tenant_id=TenantId("tenant-certificacao"),
        step_id=StepId("step-certificacao"),
        deadline=agora(),
    )
    return certificar(
        implementacao,
        entrada_para_teste_idempotencia=entrada_idempotencia,
        contexto_para_teste_idempotencia=contexto_certificacao,
    )


def _capabilities_a_registrar() -> list[tuple[CapabilityImplementation, dict[str, object]]]:
    """Uma entrada por Capability genérica migrada — `(implementação, entrada
    de teste de idempotência)`. Adicionar aqui é o único passo necessário
    para uma nova Skill entrar no scan (registro/Operador/Executor são
    genéricos em `_preparar_capabilities`, não precisam mudar)."""
    return [
        (
            construir_implementacao_regex(),
            {
                "caminho": "arquivo-de-certificacao.txt",
                "conteudo": "x",
                "regra": {
                    "codigo": "CERT-000",
                    "agente": "sistema",
                    "severidade": "low",
                    "categoria": "certificacao",
                    "titulo": "t",
                    "causa": "c",
                    "remediacao": "r",
                    "modo": "arquivo-presente",
                },
            },
        ),
        (
            construir_implementacao_ast(),
            {
                "caminho": "arquivo-de-certificacao.py",
                "conteudo": "class X:\n    pass\n",
                "regra": {
                    "codigo": "CERT-001",
                    "agente": "sistema",
                    "severidade": "low",
                    "categoria": "certificacao",
                    "titulo": "t",
                    "causa": "c",
                    "remediacao": "r",
                    "seletor_tipo": "classdef",
                    "seletor_include": "X",
                    "corpo_padrao": "protegido",
                },
            },
        ),
        (
            construir_implementacao_kwarg_ausente(),
            {
                "caminho": "arquivo-de-certificacao.py",
                "conteudo": "x = 1\n",
                "regra": {
                    "codigo": "CERT-002",
                    "agente": "sistema",
                    "severidade": "low",
                    "categoria": "certificacao",
                    "titulo": "t",
                    "causa": "c",
                    "remediacao": "r",
                    "metodos_call": ["get"],
                    "kwarg_obrigatorio": "timeout",
                },
            },
        ),
        (
            construir_implementacao_git(),
            {
                "caminho": ".git",
                "conteudo": "3",
                "regra": {
                    "codigo": "CERT-003",
                    "agente": "sistema",
                    "severidade": "low",
                    "categoria": "certificacao",
                    "titulo": "t",
                    "causa": "c",
                    "remediacao": "r",
                    "limiar": 0,
                },
            },
        ),
        (
            construir_implementacao_execucao_comando(),
            {
                "caminho": "tests/",
                "conteudo": json.dumps(
                    {
                        "returncode": 1,
                        "stdout": "1 failed",
                        "stderr": "",
                        "dir_requerido_existe": True,
                    }
                ),
                "regra": {
                    "codigo": "CERT-004",
                    "agente": "sistema",
                    "severidade": "low",
                    "categoria": "certificacao",
                    "titulo": "t",
                    "causa": "c",
                    "remediacao": "r",
                    "interpretacao": "pytest_falhou",
                },
            },
        ),
        (
            construir_implementacao_dependencias(),
            {
                "caminho": "pyproject.toml",
                "conteudo": json.dumps(
                    {
                        "pyproject_texto": '[project]\ndependencies = ["pytest>=8.0"]\n'
                        '[project.optional-dependencies]\ndev = ["pytest>=8.0"]\n',
                    }
                ),
                "regra": {
                    "codigo": "CERT-005",
                    "agente": "sistema",
                    "severidade": "low",
                    "categoria": "certificacao",
                    "titulo": "t",
                    "causa": "c",
                    "remediacao": "r",
                    "aspecto": "duplicado_prod_dev",
                },
            },
        ),
        (
            construir_implementacao_de003(),
            {
                "caminho": "api/database/tables.py",
                "conteudo": json.dumps({"aplica": False}),
                "regra": {},
            },
        ),
        (
            construir_implementacao_ora005(),
            {
                "caminho": "src/x.py",
                "conteudo": (
                    "def f():\n    try:\n        x()\n    except Exception:\n        pass\n"
                ),
                "regra": {},
            },
        ),
        (
            construir_implementacao_ora004(),
            {
                "caminho": "src/radar/models/enums.py",
                "conteudo": json.dumps({"arquivos": {}, "enums_src": None}),
                "regra": {},
            },
        ),
        (
            construir_implementacao_agregada(),
            {
                "caminho": "api",
                "conteudo": json.dumps({"arquivos": {"api/a.py": "x"}}),
                "regra": {
                    "codigo": "CERT-006",
                    "agente": "sistema",
                    "severidade": "low",
                    "categoria": "certificacao",
                    "titulo": "t",
                    "causa": "c",
                    "remediacao": "r",
                    "modo": "ausencia",
                    "pattern": "termo-que-nunca-aparece",
                    "caminho_relatado": "api",
                },
            },
        ),
        (
            construir_implementacao_janela(),
            {
                "caminho": "a.tsx",
                "conteudo": "sem trigger aqui\n",
                "regra": {
                    "codigo": "CERT-007",
                    "agente": "sistema",
                    "severidade": "low",
                    "categoria": "certificacao",
                    "titulo": "t",
                    "causa": "c",
                    "remediacao": "r",
                    "pattern_trigger": "termo-que-nunca-aparece",
                    "janela_antes": 0,
                    "janela_depois": 0,
                },
            },
        ),
        (
            construir_implementacao_metrica(),
            {
                "caminho": "a.py",
                "conteudo": "linha\n",
                "regra": {
                    "codigo": "CERT-008",
                    "agente": "sistema",
                    "severidade": "low",
                    "categoria": "certificacao",
                    "titulo": "t",
                    "causa": "c",
                    "remediacao": "r",
                    "metrica": "linhas_arquivo",
                    "limiar": 999999,
                },
            },
        ),
        (
            construir_implementacao_sup001(),
            {
                "caminho": "a.py",
                "conteudo": "x = 1\n",
                "regra": {
                    "codigo": "CERT-009",
                    "agente": "sistema",
                    "severidade": "low",
                    "categoria": "certificacao",
                    "titulo": "t",
                    "causa": "c",
                    "remediacao": "r",
                },
            },
        ),
        (
            construir_implementacao_sec005(),
            {
                "caminho": "a.py",
                "conteudo": "x = 1\n",
                "regra": {
                    "codigo": "CERT-010",
                    "agente": "sistema",
                    "severidade": "low",
                    "categoria": "certificacao",
                    "titulo": "t",
                    "causa": "c",
                    "remediacao": "r",
                },
            },
        ),
        (
            construir_implementacao_sec007(),
            {
                "caminho": "a.py",
                "conteudo": "x = 1\n",
                "regra": {
                    "codigo": "CERT-011",
                    "agente": "sistema",
                    "severidade": "low",
                    "categoria": "certificacao",
                    "titulo": "t",
                    "causa": "c",
                    "remediacao": "r",
                },
            },
        ),
        (
            construir_implementacao_be013(),
            {
                "caminho": "a.py",
                "conteudo": "x = 1\n",
                "regra": {
                    "codigo": "CERT-012",
                    "agente": "sistema",
                    "severidade": "low",
                    "categoria": "certificacao",
                    "titulo": "t",
                    "causa": "c",
                    "remediacao": "r",
                },
            },
        ),
        (
            construir_implementacao_ba004(),
            {
                "caminho": "a.py",
                "conteudo": "x = 1\n",
                "regra": {
                    "codigo": "CERT-013",
                    "agente": "sistema",
                    "severidade": "low",
                    "categoria": "certificacao",
                    "titulo": "t",
                    "causa": "c",
                    "remediacao": "r",
                },
            },
        ),
        (
            construir_implementacao_ba005(),
            {
                "caminho": "a.py",
                "conteudo": "x = 1\n",
                "regra": {
                    "codigo": "CERT-014",
                    "agente": "sistema",
                    "severidade": "low",
                    "categoria": "certificacao",
                    "titulo": "t",
                    "causa": "c",
                    "remediacao": "r",
                },
            },
        ),
        (
            construir_implementacao_arch003(),
            {
                "caminho": "pages/a.py",
                "conteudo": "x = 1\n",
                "regra": {
                    "codigo": "CERT-015",
                    "agente": "sistema",
                    "severidade": "low",
                    "categoria": "certificacao",
                    "titulo": "t",
                    "causa": "c",
                    "remediacao": "r",
                    "caminho_agregador": "dashboard/app.py",
                },
            },
        ),
        (
            construir_implementacao_feapi(),
            {
                "caminho": "api/routers/a.py",
                "conteudo": json.dumps({"api_src": "x = 1\n", "frontend_text": ""}),
                "regra": {
                    "codigo": "CERT-016",
                    "agente": "sistema",
                    "severidade": "low",
                    "categoria": "certificacao",
                    "titulo": "t",
                    "causa": "c",
                    "remediacao": "r",
                    "caminho_frontend_api": "frontend/src/api",
                },
            },
        ),
        (
            construir_implementacao_fe001(),
            {
                "caminho": "frontend/src/api",
                "conteudo": json.dumps({"arquivos": {}}),
                "regra": {
                    "codigo": "CERT-017",
                    "agente": "sistema",
                    "severidade": "low",
                    "categoria": "certificacao",
                    "titulo": "t",
                    "causa": "c",
                    "remediacao": "r",
                },
            },
        ),
        (
            construir_implementacao_be010(),
            {
                "caminho": "pyproject.toml",
                "conteudo": None,
                "regra": {
                    "codigo": "CERT-018",
                    "agente": "sistema",
                    "severidade": "low",
                    "categoria": "certificacao",
                    "titulo": "t",
                    "causa": "c",
                    "remediacao": "r",
                },
            },
        ),
        (
            construir_implementacao_pd011(),
            {
                "caminho": "frontend/src/",
                "conteudo": json.dumps({"frontend_text": "", "backend_text": ""}),
                "regra": {
                    "codigo": "CERT-019",
                    "agente": "sistema",
                    "severidade": "low",
                    "categoria": "certificacao",
                    "titulo": "t",
                    "causa": "c",
                    "remediacao": "r",
                    "pattern": "xyz-nao-deve-casar-nunca",
                    "ignore_case": False,
                },
            },
        ),
        (
            construir_implementacao_qaauto001(),
            {
                "caminho": "api/routers/__init__.py",
                "conteudo": json.dumps({"test_stems": []}),
                "regra": {
                    "codigo": "CERT-020",
                    "agente": "sistema",
                    "severidade": "low",
                    "categoria": "certificacao",
                    "titulo": "t",
                    "causa": "c",
                    "remediacao": "r",
                },
            },
        ),
        (
            construir_implementacao_a11y003(),
            {
                "caminho": "frontend/src/Nada.tsx",
                "conteudo": "<div>nada aqui</div>\n",
                "regra": {
                    "codigo": "CERT-021",
                    "agente": "sistema",
                    "severidade": "low",
                    "categoria": "certificacao",
                    "titulo": "t",
                    "causa": "c",
                    "remediacao": "r",
                },
            },
        ),
        (
            construir_implementacao_pd001(),
            {
                "caminho": "frontend/src/Nada.tsx",
                "conteudo": "<div>nada aqui</div>\n",
                "regra": {
                    "codigo": "CERT-022",
                    "agente": "sistema",
                    "severidade": "low",
                    "categoria": "certificacao",
                    "titulo": "t",
                    "causa": "c",
                    "remediacao": "r",
                },
            },
        ),
        (
            construir_implementacao_sec009(),
            {
                "caminho": "scripts/nada.py",
                "conteudo": "x = 1\n",
                "regra": {
                    "codigo": "CERT-023",
                    "agente": "sistema",
                    "severidade": "low",
                    "categoria": "certificacao",
                    "titulo": "t",
                    "causa": "c",
                    "remediacao": "r",
                },
            },
        ),
        (
            construir_implementacao_rev006(),
            {
                "caminho": "api/nada.py",
                "conteudo": "resultado_final = 1\n",
                "regra": {
                    "codigo": "CERT-024",
                    "agente": "sistema",
                    "severidade": "low",
                    "categoria": "certificacao",
                    "titulo": "t",
                    "causa": "c",
                    "remediacao": "r",
                },
            },
        ),
        (
            construir_implementacao_govdebt001(),
            {
                "caminho": "Batman/ledger.json",
                "conteudo": None,
                "regra": {
                    "codigo": "CERT-025",
                    "agente": "sistema",
                    "severidade": "low",
                    "categoria": "certificacao",
                    "titulo": "t",
                    "causa": "c",
                    "remediacao": "r",
                },
            },
        ),
        (
            construir_implementacao_sweep001(),
            {
                "caminho": "Batman/config/sweep_state.json",
                "conteudo": json.dumps(
                    {
                        "cadencia_dias": 7,
                        "atual": {
                            "papel": "security-engineer",
                            "atribuido_em": "2026-01-01T00:00:00+00:00",
                            "status": "pendente",
                        },
                    }
                ),
                "regra": {
                    "codigo": "CERT-026",
                    "agente": "sistema",
                    "severidade": "low",
                    "categoria": "certificacao",
                    "titulo": "t",
                    "causa": "c",
                    "remediacao": "r",
                },
            },
        ),
        (
            construir_implementacao_cs003(),
            {
                "caminho": "api/nada.py",
                "conteudo": "x = 1\n",
                "regra": {
                    "codigo": "CERT-027",
                    "agente": "sistema",
                    "severidade": "low",
                    "categoria": "certificacao",
                    "titulo": "t",
                    "causa": "c",
                    "remediacao": "r",
                },
            },
        ),
        (
            construir_implementacao_qaauto003(),
            {
                "caminho": "e2e/smoke",
                "conteudo": json.dumps({"missing": [], "total": 0}),
                "regra": {
                    "codigo": "CERT-028",
                    "agente": "sistema",
                    "severidade": "low",
                    "categoria": "certificacao",
                    "titulo": "t",
                    "causa": "c",
                    "remediacao": "r",
                },
            },
        ),
        (
            construir_implementacao_doc004(),
            {
                "caminho": "CHANGELOG.md",
                "conteudo": None,
                "regra": {
                    "codigo": "CERT-029",
                    "agente": "sistema",
                    "severidade": "low",
                    "categoria": "certificacao",
                    "titulo": "t",
                    "causa": "c",
                    "remediacao": "r",
                },
            },
        ),
        (
            construir_implementacao_fin005(),
            {
                "caminho": "src/nada.py",
                "conteudo": "x = 1\n",
                "regra": {
                    "codigo": "CERT-030",
                    "agente": "sistema",
                    "severidade": "low",
                    "categoria": "certificacao",
                    "titulo": "t",
                    "causa": "c",
                    "remediacao": "r",
                },
            },
        ),
        (
            construir_implementacao_sec008(),
            {
                "caminho": "api/routers/nada.py",
                "conteudo": "x = 1\n",
                "regra": {
                    "codigo": "CERT-031",
                    "agente": "sistema",
                    "severidade": "low",
                    "categoria": "certificacao",
                    "titulo": "t",
                    "causa": "c",
                    "remediacao": "r",
                },
            },
        ),
        (
            construir_implementacao_pd009(),
            {
                "caminho": "frontend/src/App.tsx",
                "conteudo": None,
                "regra": {
                    "codigo": "CERT-032",
                    "agente": "sistema",
                    "severidade": "low",
                    "categoria": "certificacao",
                    "titulo": "t",
                    "causa": "c",
                    "remediacao": "r",
                },
            },
        ),
        (
            construir_implementacao_pd010(),
            {
                "caminho": "api/routers/sim.py",
                "conteudo": "MIN_TRADE_CAPITAL = 10\n",
                "regra": {
                    "codigo": "CERT-033",
                    "agente": "sistema",
                    "severidade": "low",
                    "categoria": "certificacao",
                    "titulo": "t",
                    "causa": "c",
                    "remediacao": "r",
                    "sim_router_path": "api/routers/sim.py",
                },
            },
        ),
        (
            construir_implementacao_sre006(),
            {
                "caminho": "gunicorn.conf.py",
                "conteudo": json.dumps({"gunicorn_conf_texto": "timeout = 30\n"}),
                "regra": {
                    "codigo": "CERT-034",
                    "agente": "sistema",
                    "severidade": "low",
                    "categoria": "certificacao",
                    "titulo": "t",
                    "causa": "c",
                    "remediacao": "r",
                },
            },
        ),
        (
            construir_implementacao_cs005(),
            {
                "caminho": "api/routers/nada.py",
                "conteudo": json.dumps({"api_src": "x = 1\n", "middleware_global_texto": ""}),
                "regra": {
                    "codigo": "CERT-035",
                    "agente": "sistema",
                    "severidade": "low",
                    "categoria": "certificacao",
                    "titulo": "t",
                    "causa": "c",
                    "remediacao": "r",
                },
            },
        ),
    ]


def _preparar_capabilities() -> tuple[CapabilityRegistry, Operator]:
    """Certifica as Capabilities genéricas de verdade (checklist + testes de
    aceitação + idempotência, Vol.IV Cap.16) e monta o Operador real que as
    executa — uma vez por chamada de `executar_scan`, reaproveitado por
    todas as Missões do lote. Registra TODAS no mesmo Registry —
    `CapabilityRegistry.find_candidates` (Vol.III Cap.11) já resolve qual
    delas serve cada Missão por casamento estrutural de schema (ver
    docstring de `EntradaAst.tipo`/`EntradaKwargAusente.tipo`), sem código de
    roteamento extra aqui."""
    definicoes: list[CapabilityDefinition] = []
    implementacoes: dict[CapabilityId, CapabilityImplementation] = {}
    for implementacao, entrada_idempotencia in _capabilities_a_registrar():
        definicao = _certificar_com_idempotencia(implementacao, entrada_idempotencia)
        definicoes.append(definicao)
        implementacoes[definicao.id] = implementacao

    registry = CapabilityRegistry()
    for definicao in definicoes:
        registry.register(definicao)

    operator = Operator(
        operator_id=OperatorId("op-scan"),
        capabilities=[definicao.id for definicao in definicoes],
        permissions=PermissionSet(
            allowed_actions=[str(definicao.id) for definicao in definicoes],
            side_effect_scope=SideEffectScope.READ_ONLY,
        ),
        sandbox=SandboxPolicy(
            resource_limits=ResourceLimits(),
            network_policy=NetworkPolicy.NONE,
            filesystem_access=FilesystemAccess.NONE,
        ),
        executor=ExecutorViaImplementacoes(implementacoes),
    )
    return registry, operator


_Especificacao = (
    SpecDeRegra
    | SpecDeRegraAst
    | SpecDeRegraKwargAusente
    | SpecDeRegraGitInterpretado
    | SpecDeRegraExecucaoComando
    | SpecDeRegraDependencias
    | SpecDe003
    | SpecOra005
    | SpecOra004
    | SpecDeRegraAgregada
    | SpecDeRegraJanela
    | SpecDeRegraMetrica
    | SpecSup001
    | SpecSec005
    | SpecSec007
    | SpecBe013
    | SpecBa004
    | SpecBa005
    | SpecArch003
    | SpecFeApi
    | SpecFe001
    | SpecBe010
    | SpecPd011
    | SpecQaAuto001
    | SpecA11y003
    | SpecPd001
    | SpecSec009
    | SpecRev006
    | SpecGovdebt001
    | SpecSweep001
    | SpecCs003
    | SpecQaAuto003
    | SpecDoc004
    | SpecFin005
    | SpecSec008
    | SpecPd009
    | SpecPd010
    | SpecSre006
    | SpecCs005
)


def _todas_especificacoes() -> list[_Especificacao]:
    especificacoes: list[_Especificacao] = []
    especificacoes.extend(carregar_lote_01())
    especificacoes.extend(carregar_lote_02())
    especificacoes.extend(carregar_lote_03())
    especificacoes.extend(carregar_especificacoes_ast())
    especificacoes.extend(carregar_especificacoes_kwarg_ausente())
    especificacoes.extend(carregar_especificacoes_git_interpretado())
    especificacoes.extend(carregar_especificacoes_execucao_comando())
    especificacoes.extend(carregar_especificacoes_dependencias())
    especificacoes.extend(carregar_especificacoes_de003())
    especificacoes.extend(carregar_especificacoes_ora005())
    especificacoes.extend(carregar_especificacoes_ora004())
    especificacoes.extend(carregar_especificacoes_agregadas())
    especificacoes.extend(carregar_especificacoes_janela())
    especificacoes.extend(carregar_especificacoes_metrica())
    especificacoes.extend(carregar_especificacoes_sup001())
    especificacoes.extend(carregar_especificacoes_sec005())
    especificacoes.extend(carregar_especificacoes_sec007())
    especificacoes.extend(carregar_especificacoes_be013())
    especificacoes.extend(carregar_especificacoes_ba004())
    especificacoes.extend(carregar_especificacoes_ba005())
    especificacoes.extend(carregar_especificacoes_arch003())
    especificacoes.extend(carregar_especificacoes_feapi())
    especificacoes.extend(carregar_especificacoes_fe001())
    especificacoes.extend(carregar_especificacoes_be010())
    especificacoes.extend(carregar_especificacoes_pd011())
    especificacoes.extend(carregar_especificacoes_qaauto001())
    especificacoes.extend(carregar_especificacoes_a11y003())
    especificacoes.extend(carregar_especificacoes_pd001())
    especificacoes.extend(carregar_especificacoes_sec009())
    especificacoes.extend(carregar_especificacoes_rev006())
    especificacoes.extend(carregar_especificacoes_govdebt001())
    especificacoes.extend(carregar_especificacoes_sweep001())
    especificacoes.extend(carregar_especificacoes_cs003())
    especificacoes.extend(carregar_especificacoes_qaauto003())
    especificacoes.extend(carregar_especificacoes_doc004())
    especificacoes.extend(carregar_especificacoes_fin005())
    especificacoes.extend(carregar_especificacoes_sec008())
    especificacoes.extend(carregar_especificacoes_pd009())
    especificacoes.extend(carregar_especificacoes_pd010())
    especificacoes.extend(carregar_especificacoes_sre006())
    especificacoes.extend(carregar_especificacoes_cs005())
    return especificacoes


def executar_scan(
    root: Path,
    especificacoes: Sequence[_Especificacao] | None = None,
    db_path: str = ":memory:",
) -> ResultadoScan:
    """Vol.IX Cap.34 — roda as Capabilities migradas contra `root`. Sem
    `especificacoes`, usa todos os lotes/Skills já migrados
    (`carregar_lote_01()` + `carregar_lote_02()` + `carregar_especificacoes_ast()`
    + `carregar_especificacoes_kwarg_ausente()` +
    `carregar_especificacoes_git_interpretado()` +
    `carregar_especificacoes_execucao_comando()` +
    `carregar_especificacoes_dependencias()` +
    `carregar_especificacoes_de003()`).

    `db_path` (Milestone 5 desta construção): repassado ao `EventBus`
    interno do Mission Runtime — `":memory:"` (default) preserva o
    comportamento anterior (log descartado ao final do scan); um caminho
    real faz os eventos desta execução sobreviverem e acumularem entre
    scans sucessivos apontando para o mesmo arquivo (CLI: `--db`)."""
    especificacoes = especificacoes if especificacoes is not None else _todas_especificacoes()

    registry, operator = _preparar_capabilities()
    execution_engine = ExecutionEngine(
        validador_schema=ValidadorSchemaEstrutural(),
        validador_contrato_nao_deterministico=ValidadorContratoSempreAprova(),
    )
    runtime = MissionRuntime(EventBus(db_path=db_path), tipos=_registro_tipos())
    decision_engine = DecisionEngine(
        base_conhecimento=_SemConhecimentoAinda(),
        llm_gateway=_LlmNuncaChamadoNesteFluxo(),
        validador=_ValidadorSempreAprova(),
    )
    adapter = OperadorExecutavelAdapter(operator)
    operator_ref = OperatorRef(operator_id=operator.id)

    resultado = ResultadoScan()
    try:
        for item in especificacoes:
            regra = item["regra"]
            entradas: Sequence[
                EntradaRegexArquivo
                | EntradaAst
                | EntradaKwargAusente
                | EntradaGitInterpretado
                | EntradaExecucaoComando
                | EntradaDependencias
                | EntradaDe003
                | EntradaOra005
                | EntradaOra004
                | EntradaAgregada
                | EntradaJanela
                | EntradaMetrica
                | EntradaSup001
                | EntradaSec005
                | EntradaSec007
                | EntradaBe013
                | EntradaBa004
                | EntradaBa005
                | EntradaArch003
                | EntradaFeApi
                | EntradaFe001
                | EntradaBe010
                | EntradaPd011
                | EntradaQaAuto001
                | EntradaA11y003
                | EntradaPd001
                | EntradaSec009
                | EntradaRev006
                | EntradaGovdebt001
                | EntradaSweep001
                | EntradaCs003
                | EntradaQaAuto003
                | EntradaDoc004
                | EntradaFin005
                | EntradaSec008
                | EntradaPd009
                | EntradaPd010
                | EntradaSre006
                | EntradaCs005
            ]
            if isinstance(regra, RegraAstSpec):
                entradas = entradas_ast_para_regra(root, regra, item["descoberta"])
            elif isinstance(regra, RegraKwargAusenteSpec):
                entradas = entradas_kwarg_ausente_para_regra(root, regra, item["descoberta"])
            elif isinstance(regra, RegraComparacaoNumericaSpec):
                entradas = entradas_git_interpretado_para_regra(root, regra, item["descoberta"])
            elif isinstance(regra, RegraExecucaoComandoSpec):
                entradas = entradas_execucao_comando_para_regra(root, regra, item["descoberta"])
            elif isinstance(regra, RegraDependenciasSpec):
                entradas = entradas_dependencias_para_regra(root, regra, item["descoberta"])
            elif isinstance(regra, RegraDe003Spec):
                entradas = entradas_de003_para_regra(root, regra, item["descoberta"])
            elif isinstance(regra, RegraOra005Spec):
                entradas = entradas_ora005_para_regra(root, regra, item["descoberta"])
            elif isinstance(regra, RegraOra004Spec):
                entradas = entradas_ora004_para_regra(root, regra, item["descoberta"])
            elif isinstance(regra, RegraAgregadaSpec):
                entradas = entradas_agregadas_para_regra(root, regra, item["descoberta"])
            elif isinstance(regra, RegraJanelaSpec):
                entradas = entradas_janela_para_regra(root, regra, item["descoberta"])
            elif isinstance(regra, RegraMetricaSpec):
                entradas = entradas_metrica_para_regra(root, regra, item["descoberta"])
            elif isinstance(regra, RegraSup001Spec):
                entradas = entradas_sup001_para_regra(root, regra, item["descoberta"])
            elif isinstance(regra, RegraSec005Spec):
                entradas = entradas_sec005_para_regra(root, regra, item["descoberta"])
            elif isinstance(regra, RegraSec007Spec):
                entradas = entradas_sec007_para_regra(root, regra, item["descoberta"])
            elif isinstance(regra, RegraBe013Spec):
                entradas = entradas_be013_para_regra(root, regra, item["descoberta"])
            elif isinstance(regra, RegraBa004Spec):
                entradas = entradas_ba004_para_regra(root, regra, item["descoberta"])
            elif isinstance(regra, RegraBa005Spec):
                entradas = entradas_ba005_para_regra(root, regra, item["descoberta"])
            elif isinstance(regra, RegraArch003Spec):
                entradas = entradas_arch003_para_regra(root, regra, item["descoberta"])
            elif isinstance(regra, RegraFeApiSpec):
                entradas = entradas_feapi_para_regra(root, regra, item["descoberta"])
            elif isinstance(regra, RegraFe001Spec):
                entradas = entradas_fe001_para_regra(root, regra, item["descoberta"])
            elif isinstance(regra, RegraBe010Spec):
                entradas = entradas_be010_para_regra(root, regra, item["descoberta"])
            elif isinstance(regra, RegraPd011Spec):
                entradas = entradas_pd011_para_regra(root, regra, item["descoberta"])
            elif isinstance(regra, RegraQaAuto001Spec):
                entradas = entradas_qaauto001_para_regra(root, regra, item["descoberta"])
            elif isinstance(regra, RegraA11y003Spec):
                entradas = entradas_a11y003_para_regra(root, regra, item["descoberta"])
            elif isinstance(regra, RegraPd001Spec):
                entradas = entradas_pd001_para_regra(root, regra, item["descoberta"])
            elif isinstance(regra, RegraSec009Spec):
                entradas = entradas_sec009_para_regra(root, regra, item["descoberta"])
            elif isinstance(regra, RegraRev006Spec):
                entradas = entradas_rev006_para_regra(root, regra, item["descoberta"])
            elif isinstance(regra, RegraGovdebt001Spec):
                entradas = entradas_govdebt001_para_regra(root, regra, item["descoberta"])
            elif isinstance(regra, RegraSweep001Spec):
                entradas = entradas_sweep001_para_regra(root, regra, item["descoberta"])
            elif isinstance(regra, RegraCs003Spec):
                entradas = entradas_cs003_para_regra(root, regra, item["descoberta"])
            elif isinstance(regra, RegraQaAuto003Spec):
                entradas = entradas_qaauto003_para_regra(root, regra, item["descoberta"])
            elif isinstance(regra, RegraDoc004Spec):
                entradas = entradas_doc004_para_regra(root, regra, item["descoberta"])
            elif isinstance(regra, RegraFin005Spec):
                entradas = entradas_fin005_para_regra(root, regra, item["descoberta"])
            elif isinstance(regra, RegraSec008Spec):
                entradas = entradas_sec008_para_regra(root, regra, item["descoberta"])
            elif isinstance(regra, RegraPd009Spec):
                entradas = entradas_pd009_para_regra(root, regra, item["descoberta"])
            elif isinstance(regra, RegraPd010Spec):
                entradas = entradas_pd010_para_regra(root, regra, item["descoberta"])
            elif isinstance(regra, RegraSre006Spec):
                entradas = entradas_sre006_para_regra(root, regra, item["descoberta"])
            elif isinstance(regra, RegraCs005Spec):
                entradas = entradas_cs005_para_regra(root, regra, item["descoberta"])
            else:
                entradas = entradas_para_regra(root, regra, item["descoberta"])
            for entrada in entradas:
                achados_da_entrada = _processar_entrada(
                    entrada.model_dump(),
                    runtime=runtime,
                    registry=registry,
                    decision_engine=decision_engine,
                    execution_engine=execution_engine,
                    adapter=adapter,
                    operator_ref=operator_ref,
                )
                resultado.achados.extend(achados_da_entrada)
    finally:
        execution_engine.fechar()
    return resultado


def _processar_entrada(
    entrada: dict[str, object],
    *,
    runtime: MissionRuntime,
    registry: CapabilityRegistry,
    decision_engine: DecisionEngine,
    execution_engine: ExecutionEngine,
    adapter: OperadorExecutavelAdapter,
    operator_ref: OperatorRef,
) -> list[AchadoScan]:
    """Uma Missão real, do início ao fim, para um único (arquivo, regra).

    Retorna TODOS os achados da Missão, não só o primeiro (achado da
    validação de FE-API: uma Missão pode legitimamente produzir MÚLTIPLOS
    achados — ex.: várias rotas ausentes no mesmo arquivo, cada uma com
    `chave` distinta — `saida["achados"][0]` descartava silenciosamente
    os demais)."""
    mission = runtime.create(MissionIntent(dados=entrada), TIPO_MISSAO, tenant_id=TENANT_PADRAO)
    runtime.transition(mission.id, MissionEventType.PLANNING_STARTED)

    plano = plan(
        mission_id=mission.id, tenant_id=TENANT_PADRAO, intent=mission.intent, registro=registry
    )
    if not plano.steps:
        runtime.transition(mission.id, MissionEventType.PLAN_FAILED)
        return []
    runtime.transition(mission.id, MissionEventType.PLAN_READY)

    runtime.transition(mission.id, MissionEventType.DECIDING_STARTED)
    for ponto in plano.decision_points:
        decision_engine.resolve(ponto, mission.id)
    runtime.transition(mission.id, MissionEventType.DECISIONS_RESOLVED)

    tabela = TabelaDeEntradasPorStep()
    tabela.registrar(plano.steps[0].id, entrada)
    invocador = InvocadorDeStepPadrao(
        execution_engine=execution_engine,
        adapter=adapter,
        operator_ref=operator_ref,
        capability_registry=registry,
        tabela_entradas=tabela,
        mission_id=mission.id,
        tenant_id=TENANT_PADRAO,
    )
    workflow = WorkflowEngine(invocador)
    run = workflow.iniciar(mission.id, plano)
    while workflow.get_run(run.id).estado == "running":
        prontos = workflow.passos_prontos(run.id)
        if not prontos:
            break
        workflow.executar_passo(run.id, prontos[0])

    if workflow.get_run(run.id).estado != "completed":
        runtime.transition(mission.id, MissionEventType.WORKFLOW_FAILED)
        return []

    runtime.transition(mission.id, MissionEventType.WORKFLOW_COMPLETED)
    saida = workflow.get_run(run.id).completed_steps[0].output
    if not saida or not saida.get("achados"):
        return []
    return [AchadoScan(**item) for item in saida["achados"]]
