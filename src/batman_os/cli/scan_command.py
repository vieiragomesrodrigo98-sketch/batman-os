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

import logging
import subprocess
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

from batman_os.capabilities import registry_sdk
from batman_os.capabilities.capability_contract import (
    CapabilityImplementation,
    GapDeChecklist,
    ResultadoEsperado,
    certificar,
)
from batman_os.capabilities.isencoes import (
    IsencaoPreRegistrada,
    carregar_isencoes,
    filtrar_achados_isentos,
)
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
from batman_os.cli.descoberta_arquivos import (
    DEFAULT_EXCLUDED_DIRS,
    EstatisticasDeDescoberta,
    calcular_estatisticas_de_descoberta,
    escopo_de_exclusao_de_diretorios,
    registrar_capabilities_conhecidas,
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
from batman_os.governance.inbox import AchadoInboxEntrada
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

logger = logging.getLogger(__name__)


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
    duracoes_por_capability: dict[str, list[float]] = field(default_factory=dict)
    estatisticas_de_descoberta: EstatisticasDeDescoberta | None = None

    def contagem_por_severidade(self) -> dict[str, int]:
        contagem: dict[str, int] = {}
        for achado in self.achados:
            contagem[achado.severidade] = contagem.get(achado.severidade, 0) + 1
        return contagem

    def resumo_de_performance(self) -> dict[str, dict[str, float]]:
        """Fase 1 do roadmap de plataforma ("Capability Timeline") --
        agrega os tempos de execucao por Capability atraves de todas as
        Missoes do scan. Nao adiciona instrumentacao nova: os tempos ja
        sao medidos nativamente por `StepResult.iniciado_em`/
        `finalizado_em` (Vol.II Cap.9) para cada step -- aqui so
        agregamos o que ja existe."""
        resumo: dict[str, dict[str, float]] = {}
        for capability_id, duracoes in self.duracoes_por_capability.items():
            resumo[capability_id] = {
                "chamadas": float(len(duracoes)),
                "total_ms": sum(duracoes),
                "media_ms": sum(duracoes) / len(duracoes),
                "max_ms": max(duracoes),
            }
        return resumo


def achados_para_inbox(resultado: ResultadoScan) -> list[AchadoInboxEntrada]:
    """Adaptador `AchadoScan` -> `AchadoInboxEntrada` (`governance/
    inbox.py`, capacidade "Inbox" de fila persistente de achados). Vive
    AQUI, não em `governance/inbox.py`, porque `governance/` nunca importa
    de `cli/` (Vol.VIII Cap.32, seção 32.3 — mesma disciplina de camadas
    que "workflow depende de kernel, nunca o contrário"); quem conhece
    `AchadoScan` é este módulo, então o adaptador mora do lado de quem já
    conhece o tipo concreto.

    `chave_dominio` = `codigo|arquivo|chave` — identidade de domínio do
    achado dentro do scan (`chave` já é o discriminador que várias regras
    usam para distinguir múltiplos achados da MESMA dupla (regra,
    arquivo), ex.: `fe001_export_duplicado.py`, `feapi_rota_sem_
    frontend.py` — "" quando a regra produz no máximo um achado por
    arquivo)."""
    return [
        AchadoInboxEntrada(
            chave_dominio=f"{achado.codigo}|{achado.arquivo}|{achado.chave}",
            severidade=Criticidade(achado.severidade),
            titulo=f"{achado.codigo} {achado.arquivo}: {achado.titulo}",
            detalhe=achado.descricao or achado.titulo,
        )
        for achado in resultado.achados
    ]


class RaizSemGitError(Exception):
    """`--changed` (CLI, Pacote 3 do roadmap de CLI) exige um repositório
    git real em `root` para saber o que mudou -- levantada por
    `arquivos_alterados_via_git` quando `git` não está no PATH, `root` não
    é um repositório git, ou o `ref` pedido não resolve (ex.: repositório
    sem nenhum commit ainda, onde `git diff --name-only HEAD` falha). Sem
    isso, a única opção segura é pedir o scan completo (`batman scan` sem
    `--changed`) -- `batman.py::_comando_scan` captura e imprime a
    mensagem, retornando código de saída 1."""


def arquivos_alterados_via_git(root: Path, ref: str | None = None) -> frozenset[str]:
    """Conjunto de caminhos relativos (posix, mesmo formato de
    `descoberta_arquivos.py::_rel_posix`) alterados em `root` -- união de
    `git status --porcelain` (working tree: modificados + staged +
    untracked) com `git diff --name-only <ref>` (`ref` default `"HEAD"`,
    ou seja "working tree vs HEAD"; `--changed-ref` da CLI sobrescreve
    para comparar contra outro ponto, ex. a branch base de um PR).

    A união existe porque `git diff --name-only HEAD` sozinho NÃO lista
    arquivos untracked (novos, nunca adicionados ao índice) -- só
    `status --porcelain` os enxerga; e `status --porcelain` sozinho não
    cobre comparar contra um ref diferente de HEAD. Usado por
    `executar_scan(arquivos_alterados=...)` para filtrar as entradas de
    descoberta `"arvore"`/`"glob"` (ver `_TIPOS_FILTRAVEIS_POR_ARQUIVO`)."""
    ref_efetivo = ref if ref is not None else "HEAD"
    alterados: set[str] = set()
    alterados.update(_arquivos_via_status_porcelain(root))
    alterados.update(_arquivos_via_diff(root, ref_efetivo))
    return frozenset(alterados)


def _rodar_git(root: Path, *args: str) -> str:
    try:
        resultado = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RaizSemGitError(
            "'git' não encontrado no PATH -- '--changed' exige git instalado; "
            "rode 'batman scan' sem '--changed' para o scan completo"
        ) from exc
    if resultado.returncode != 0:
        raise RaizSemGitError(
            f"'git {' '.join(args)}' falhou em '{root}' ({resultado.stderr.strip()}) -- "
            "'--changed' exige um repositório git válido (com pelo menos um commit); "
            "rode 'batman scan' sem '--changed' para o scan completo"
        )
    return resultado.stdout


def _arquivos_via_status_porcelain(root: Path) -> set[str]:
    saida = _rodar_git(root, "status", "--porcelain")
    alterados: set[str] = set()
    for linha in saida.splitlines():
        if not linha:
            continue
        caminho = linha[3:]
        if " -> " in caminho:  # rename/copy: "<status> old -> new"
            caminho = caminho.split(" -> ", 1)[1]
        alterados.add(_normalizar_caminho_git(caminho))
    return alterados


def _arquivos_via_diff(root: Path, ref: str) -> set[str]:
    saida = _rodar_git(root, "diff", "--name-only", ref)
    return {_normalizar_caminho_git(linha) for linha in saida.splitlines() if linha}


def _normalizar_caminho_git(caminho: str) -> str:
    caminho = caminho.strip()
    if len(caminho) >= 2 and caminho[0] == '"' and caminho[-1] == '"':
        caminho = caminho[1:-1]
    return caminho


_INTERVALO_LOG_PROGRESSO_SEGUNDOS = 30.0
_FRACAO_LOG_PROGRESSO_PERCENTUAL = 0.05  # ~1x a cada 5% do total de Missões


class _RastreadorDeProgresso:
    """Progresso + ETA do scan (Pacote 3 do roadmap de CLI) -- loga a cada
    ~5% do total de Missões OU a cada 30s (o que vier primeiro), sem custo
    mensurável por Missão: só um contador e uma chamada a
    `time.monotonic()` em `registrar()`, nenhuma I/O extra -- o log em si
    (a única parte com custo real) só roda quando um dos dois limiares é
    cruzado. Silencioso quando `quiet=True` ou quando não há nenhuma
    Missão a processar (`total == 0`)."""

    def __init__(self, total: int, quiet: bool) -> None:
        self._total = total
        self._quiet = quiet or total == 0
        self._concluidas = 0
        self._achados = 0
        self._inicio = time.monotonic()
        self._ultimo_log = self._inicio
        self._passo_percentual = max(1, round(total * _FRACAO_LOG_PROGRESSO_PERCENTUAL))
        self._proximo_marco = self._passo_percentual

    def registrar(self, novos_achados: int) -> None:
        self._concluidas += 1
        self._achados += novos_achados
        if self._quiet:
            return
        agora = time.monotonic()
        e_a_ultima = self._concluidas >= self._total
        atingiu_percentual = self._concluidas >= self._proximo_marco
        atingiu_tempo = (agora - self._ultimo_log) >= _INTERVALO_LOG_PROGRESSO_SEGUNDOS
        if not (e_a_ultima or atingiu_percentual or atingiu_tempo):
            return
        self._logar(agora)
        self._ultimo_log = agora
        while self._proximo_marco <= self._concluidas:
            self._proximo_marco += self._passo_percentual

    def _logar(self, agora: float) -> None:
        decorrido = agora - self._inicio
        percentual = round((self._concluidas / self._total) * 100)
        restantes = self._total - self._concluidas
        eta = (decorrido / self._concluidas) * restantes if self._concluidas else 0.0
        logger.info(
            "scan: %s/%s missões (%d%%) · %s decorridos · ETA ~%s · achados até aqui: %d",
            _formatar_milhar(self._concluidas),
            _formatar_milhar(self._total),
            percentual,
            _formatar_duracao(decorrido),
            _formatar_duracao(eta),
            self._achados,
        )


def _formatar_milhar(numero: int) -> str:
    return f"{numero:,}".replace(",", ".")


def _formatar_duracao(segundos: float) -> str:
    total_segundos = max(0, int(segundos))
    minutos, segs = divmod(total_segundos, 60)
    if minutos:
        return f"{minutos}m{segs:02d}s"
    return f"{segs}s"


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


def _entrada_de_idempotencia(implementacao: CapabilityImplementation) -> dict[str, object]:
    """Reaproveita o primeiro teste de aceitacao SUCCESS da propria
    Capability como payload do teste de idempotencia (AT-16.3) -- elimina
    o mecanismo antigo de ~46 payloads CERT-NNN hand-crafted em
    `scan_command.py` (Fase 1 do roadmap de plataforma, ver `.claude/
    plans/peaceful-wondering-hearth.md`). Seguro porque toda Capability
    migrada e `side_effects=none` -- repetir a mesma entrada valida
    produz a mesma saida, nao e um caminho especial de teste."""
    for teste in implementacao.acceptance_tests:
        if teste.resultado_esperado == ResultadoEsperado.SUCCESS:
            return dict(teste.entrada)
    raise GapDeChecklist(
        f"Capability '{implementacao.definition.id}' sem teste SUCCESS para "
        "derivar o payload de idempotencia (AT-16.3)"
    )


def _preparar_capabilities() -> tuple[CapabilityRegistry, Operator]:
    """Certifica todas as Capabilities registradas (checklist + testes de
    aceitacao + idempotencia, Vol.IV Cap.16) e monta o Operador real que as
    executa -- uma vez por chamada de `executar_scan`, reaproveitado por
    todas as Missoes do lote. Registra TODAS no mesmo Registry --
    `CapabilityRegistry.find_candidates` (Vol.III Cap.11) ja resolve qual
    delas serve cada Missao por casamento estrutural de schema, sem
    codigo de roteamento extra aqui.

    Fonte das Capabilities: `registry_sdk.registry()`, populado por
    `descoberta_arquivos.py::registrar_capabilities_conhecidas()` -- unico
    ponto de registro necessario para uma Capability nova (Fase 1 do
    roadmap de plataforma)."""
    if not registry_sdk.registry():
        registrar_capabilities_conhecidas()

    definicoes: list[CapabilityDefinition] = []
    implementacoes: dict[CapabilityId, CapabilityImplementation] = {}
    for plugin in registry_sdk.registry().values():
        implementacao = plugin.construir_implementacao()
        entrada_idempotencia = _entrada_de_idempotencia(implementacao)
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


def _todas_especificacoes() -> list[Any]:
    """Concatena os specs de TODAS as Capabilities registradas --
    substitui a lista manual de ~48 `especificacoes.extend(...)` (Fase 1
    do roadmap de plataforma). Cada item mantem o mesmo shape de sempre
    (`{"regra": RegraXSpec, "descoberta": dict}`), sem tag de `tipo` --
    compatibilidade total com quem ja chama
    `executar_scan(especificacoes=carregar_especificacoes_x())`
    diretamente (`tests/cli/test_scan_command.py`)."""
    especificacoes: list[Any] = []
    for plugin in registry_sdk.registry().values():
        especificacoes.extend(plugin.carregar_especificacoes())
    return especificacoes


_TIPOS_FILTRAVEIS_POR_ARQUIVO = frozenset({"arvore", "glob"})
"""Tipos de descoberta (`descoberta_arquivos.py::arquivos_para_regra`) que
enumeram arquivos individuais sob `scope_dirs`/`padroes` -- 230 dos 282
specs atuais (medido 2026-07, `grep` sobre `specs/**/*.json`), a maioria
esmagadora das Missões de um scan real. São os únicos filtrados por
`executar_scan(arquivos_alterados=...)` (`--changed` da CLI): os demais
tipos (`arquivo_fixo`, `git`, `subprocess`, `toml_dependencias`,
`regex_agregado`, e as ~13 bespoke tipo `de003`/`ora004`/`feapi`/...) são
checagens de projeto/árvore inteira -- existência de UM arquivo fixo,
comando único, agregação através de TODOS os arquivos -- que não têm como
se decompor em "só este arquivo mudou" sem mudar o que a regra significa,
então rodam sempre (decisão de design do Pacote 3 do roadmap de CLI)."""


def executar_scan(
    root: Path,
    especificacoes: Sequence[Any] | None = None,
    db_path: str = ":memory:",
    paralelo: bool = False,
    max_workers: int = 8,
    tenant_id: TenantId = TENANT_PADRAO,
    excluir_dirs: frozenset[str] | None = None,
    usar_excludes_padrao: bool = True,
    arquivos_alterados: frozenset[str] | None = None,
    quiet: bool = False,
    isencoes: list[IsencaoPreRegistrada] | None = None,
) -> ResultadoScan:
    """Vol.IX Cap.34 -- roda as Capabilities migradas contra `root`. Sem
    `especificacoes`, usa os specs de todas as Capabilities registradas
    (`registry_sdk.registry()`, populado por `descoberta_arquivos.py::
    registrar_capabilities_conhecidas()`).

    `db_path` (Milestone 5 desta construcao): repassado ao `EventBus`
    interno do Mission Runtime -- `":memory:"` (default) preserva o
    comportamento anterior (log descartado ao final do scan); um caminho
    real faz os eventos desta execucao sobreviverem e acumularem entre
    scans sucessivos apontando para o mesmo arquivo (CLI: `--db`).

    `paralelo`/`max_workers` (Fase 2 do roadmap de plataforma, `.claude/
    plans/peaceful-wondering-hearth.md`, Estagio 2.4) -- opt-in, default
    `False` preserva 100% do caminho sequencial anterior (mesma ordem de
    processamento, achado por achado). Quando `True`, cada (arquivo, regra)
    vira uma Missao processada de forma concorrente via ThreadPoolExecutor
    -- seguro desde que EventBus/ExecutionEngine/adapter (Estagio 2.3) e os
    contadores do DecisionEngine (Estagio 2.4) ja sao thread-safe, e toda
    Capability migrada e `side_effects=none` (nunca muta estado compartilhado
    fora do que os Protocols de borda ja isolam). Resultado final e o MESMO
    conjunto de achados que o caminho sequencial -- so a ORDEM de conclusao
    pode variar, nunca testada como garantia (`tests/cli/test_scan_command.py`
    compara por conjunto).

    `tenant_id` (Fase 5 do roadmap de plataforma, Estagio 5.3) -- opcional,
    default `TENANT_PADRAO` preserva 100% do comportamento atual; CLI:
    `--tenant`.

    `excluir_dirs`/`usar_excludes_padrao` -- nomes de diretorio podados da
    travessia de TODA descoberta recursiva (`descoberta_arquivos.py::
    DEFAULT_EXCLUDED_DIRS` -- `.venv`, `node_modules`, `__pycache__`, ...).
    `usar_excludes_padrao=True` (default) aplica `DEFAULT_EXCLUDED_DIRS`;
    `excluir_dirs` (default `None` == nenhum extra) SOMA a ela. CLI:
    `--exclude NOME` (repetivel) preenche `excluir_dirs`; `--no-default-
    excludes` vira `usar_excludes_padrao=False` (escape hatch -- volta a
    travessia completa desta funcao antes desta mudanca, ou uma lista
    100% customizada se combinado com `--exclude`).

    `arquivos_alterados` (Pacote 3 do roadmap de CLI, `--changed`) --
    quando informado (nao `None`), filtra as entradas de descoberta
    `"arvore"`/`"glob"` para so as cujo `caminho` aparece neste conjunto
    (ver `_TIPOS_FILTRAVEIS_POR_ARQUIVO` para a decisao de design de quais
    tipos sao filtraveis); default `None` preserva 100% do comportamento
    anterior (nenhuma flag existia antes desta mudanca). CLI: `--changed`
    popula via `arquivos_alterados_via_git`.

    `quiet` (Pacote 3) -- desliga o log de progresso/ETA
    (`_RastreadorDeProgresso`, a cada ~5% do total de Missoes ou 30s, o
    que vier primeiro); `batman.py::_comando_scan` reaproveita a mesma
    flag para tambem desligar a impressao do `resumo_de_performance()` ao
    final. Default `False` preserva o comportamento anterior (o log de
    progresso e novo nesta mudanca -- sem flag nenhuma antes, o unico
    comportamento possivel era "logar").

    `isencoes` (Onda 1 do Plano Cobertura Total, recalibracao de regras,
    S162) -- filtra do resultado achados cujo (codigo, arquivo) tenha uma
    isencao pre-registrada valida (`capabilities/isencoes.py`). `None`
    (default) carrega `isencoes_pre_registradas.json` automaticamente --
    e o comportamento em producao; testes que queiram ver o achado "cru"
    passam `isencoes=[]` explicitamente."""
    excludes_finais = (DEFAULT_EXCLUDED_DIRS if usar_excludes_padrao else frozenset[str]()) | (
        excluir_dirs or frozenset[str]()
    )
    with escopo_de_exclusao_de_diretorios(excludes_finais):
        # Visibilidade obrigatoria no inicio do scan -- silencio aqui
        # esconde regressao de performance (ex.: um `scope_dirs` novo
        # apontando pra raiz sem querer, ou uma exclusao nova quebrada).
        estatisticas = calcular_estatisticas_de_descoberta(root, excludes_finais)
        logger.info(
            "scan %s: %d arquivo(s) enumerados, %d diretorio(s) podado(s) (exclusoes=%s)",
            root,
            estatisticas.arquivos_enumerados,
            estatisticas.diretorios_podados,
            sorted(excludes_finais) if excludes_finais else "nenhuma",
        )

        if not registry_sdk.registry():
            registrar_capabilities_conhecidas()
        especificacoes = especificacoes if especificacoes is not None else _todas_especificacoes()

        registry, operator = _preparar_capabilities()
        dispatch_por_regra = registry_sdk.registry_por_regra_cls()
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
        operator_ref = OperatorRef(operator_id=operator.id)

        resultado = ResultadoScan(estatisticas_de_descoberta=estatisticas)
        try:
            entradas_para_processar: list[dict[str, object]] = []
            for item in especificacoes:
                regra = item["regra"]
                descoberta = item["descoberta"]
                plugin = dispatch_por_regra.get(type(regra))
                if plugin is None:
                    raise ValueError(
                        f"regra do tipo {type(regra).__name__} nao tem Capability registrada "
                        "(ver descoberta_arquivos.py::registrar_capabilities_conhecidas)"
                    )
                entradas = plugin.entradas_para_regra(root, regra, descoberta)
                if (
                    arquivos_alterados is not None
                    and descoberta.get("tipo") in _TIPOS_FILTRAVEIS_POR_ARQUIVO
                ):
                    entradas = [
                        entrada for entrada in entradas if entrada.caminho in arquivos_alterados
                    ]
                entradas_para_processar.extend(entrada.model_dump() for entrada in entradas)

            def _processar(entrada: dict[str, object]) -> ResultadoMissao:
                return _processar_entrada(
                    entrada,
                    runtime=runtime,
                    registry=registry,
                    decision_engine=decision_engine,
                    execution_engine=execution_engine,
                    operator=operator,
                    operator_ref=operator_ref,
                    tenant_id=tenant_id,
                )

            rastreador = _RastreadorDeProgresso(total=len(entradas_para_processar), quiet=quiet)
            resultados_missao: list[ResultadoMissao] = []
            if paralelo:
                with ThreadPoolExecutor(max_workers=max_workers) as pool:
                    for resultado_missao in pool.map(_processar, entradas_para_processar):
                        resultados_missao.append(resultado_missao)
                        rastreador.registrar(len(resultado_missao.achados))
            else:
                for entrada in entradas_para_processar:
                    resultado_missao = _processar(entrada)
                    resultados_missao.append(resultado_missao)
                    rastreador.registrar(len(resultado_missao.achados))

            for resultado_missao in resultados_missao:
                resultado.achados.extend(resultado_missao.achados)
                if resultado_missao.capability_id is not None and (
                    resultado_missao.duracao_ms is not None
                ):
                    resultado.duracoes_por_capability.setdefault(
                        resultado_missao.capability_id, []
                    ).append(resultado_missao.duracao_ms)
        finally:
            execution_engine.fechar()
        isencoes_aplicadas = isencoes if isencoes is not None else carregar_isencoes()
        resultado.achados = filtrar_achados_isentos(resultado.achados, isencoes_aplicadas)
        return resultado


@dataclass
class ResultadoMissao:
    """Achados + observabilidade de uma unica Missao (Fase 1 do roadmap
    de plataforma) -- `capability_id`/`duracao_ms` vem direto do
    `StepResult` que o Workflow Engine ja mede nativamente (Vol.II
    Cap.9), sem instrumentacao nova."""

    achados: list[AchadoScan] = field(default_factory=list)
    capability_id: str | None = None
    duracao_ms: float | None = None


def _processar_entrada(
    entrada: dict[str, object],
    *,
    runtime: MissionRuntime,
    registry: CapabilityRegistry,
    decision_engine: DecisionEngine,
    execution_engine: ExecutionEngine,
    operator: Operator,
    operator_ref: OperatorRef,
    tenant_id: TenantId,
) -> ResultadoMissao:
    """Uma Missão real, do início ao fim, para um único (arquivo, regra).

    Retorna TODOS os achados da Missão, não só o primeiro (achado da
    validação de FE-API: uma Missão pode legitimamente produzir MÚLTIPLOS
    achados — ex.: várias rotas ausentes no mesmo arquivo, cada uma com
    `chave` distinta — `saida["achados"][0]` descartava silenciosamente
    os demais)."""
    mission = runtime.create(MissionIntent(dados=entrada), TIPO_MISSAO, tenant_id=tenant_id)
    runtime.transition(mission.id, MissionEventType.PLANNING_STARTED, tenant_id)

    plano = plan(
        mission_id=mission.id, tenant_id=tenant_id, intent=mission.intent, registro=registry
    )
    if not plano.steps:
        runtime.transition(mission.id, MissionEventType.PLAN_FAILED, tenant_id)
        return ResultadoMissao()
    runtime.transition(
        mission.id,
        MissionEventType.PLAN_READY,
        tenant_id,
        payload_extra={"capability_id": str(plano.steps[0].capability.capability_id)},
    )

    runtime.transition(mission.id, MissionEventType.DECIDING_STARTED, tenant_id)
    for ponto in plano.decision_points:
        decision_engine.resolve(ponto, mission.id)
    runtime.transition(mission.id, MissionEventType.DECISIONS_RESOLVED, tenant_id)

    tabela = TabelaDeEntradasPorStep()
    tabela.registrar(plano.steps[0].id, entrada)
    invocador = InvocadorDeStepPadrao(
        execution_engine=execution_engine,
        operator=operator,
        operator_ref=operator_ref,
        capability_registry=registry,
        tabela_entradas=tabela,
        mission_id=mission.id,
        tenant_id=tenant_id,
    )
    workflow = WorkflowEngine(invocador)
    run = workflow.iniciar(mission.id, plano)
    while workflow.get_run(run.id).estado == "running":
        prontos = workflow.passos_prontos(run.id)
        if not prontos:
            break
        workflow.executar_passo(run.id, prontos[0], tenant_id)

    if workflow.get_run(run.id).estado != "completed":
        runtime.transition(mission.id, MissionEventType.WORKFLOW_FAILED, tenant_id)
        return ResultadoMissao()

    step_result = workflow.get_run(run.id).completed_steps[0]
    duracao_ms = (step_result.finalizado_em - step_result.iniciado_em).total_seconds() * 1000
    capability_id = str(plano.steps[0].capability.capability_id)
    runtime.transition(
        mission.id,
        MissionEventType.WORKFLOW_COMPLETED,
        tenant_id,
        payload_extra={"capability_id": capability_id, "duracao_ms": round(duracao_ms, 3)},
    )
    saida = step_result.output
    if not saida or not saida.get("achados"):
        return ResultadoMissao(capability_id=capability_id, duracao_ms=duracao_ms)
    return ResultadoMissao(
        achados=[AchadoScan(**item) for item in saida["achados"]],
        capability_id=capability_id,
        duracao_ms=duracao_ms,
    )
