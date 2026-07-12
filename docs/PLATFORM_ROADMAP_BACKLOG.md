# Roadmap de Plataforma — Status e Backlog

> Registro formal e portável (versionado no repo) do roadmap de plataforma que
> levou o Batman OS de "Scanner Determinístico" a "Plataforma Operacional de
> Engenharia". O plano de execução completo (achados de investigação, decisões
> de escopo estágio a estágio) viveu numa sessão de planejamento local
> (`.claude/plans/`, não versionado) — este documento é o resumo durável que
> sobrevive fora dessa sessão.

## Status: ROADMAP FECHADO (2026-07-12)

Fases 1–11 concluídas e commitadas. **1058 testes, `mypy`/`ruff` limpos,
working tree limpo.** Todo candidato de tamanho "fase inteira" identificado
por investigação foi implementado, descartado com justificativa registrada, ou
recusado explicitamente pelo autor (ver Backlog abaixo). Não há mais candidato
do tamanho de uma fase pendente — só itens pequenos, documentados como
exclusão deliberada.

Isso **não significa que o Batman OS esteja "pronto" ou em produção** — ver
seção "O que continua fora de escopo" no final.

## O que existe hoje (resultado das Fases 1–11)

- **Núcleo do Kernel** (Volumes I–VII da spec): Mission Runtime, Planning/
  Decision/Workflow Engine, Event Bus, Scheduler, Capability Engine,
  Execution Engine, Operational Memory, Knowledge Graph, Rule/Workflow
  Evolution, Governance Engine — todos com persistência real via SQLite
  (`EventBus`/`OperationalMemory`), thread-safe, com paralelismo real
  (`runtime/dispatcher.py`).
- **Isolamento multi-tenant estrutural** — não só carregado, mas VALIDADO: nos
  acessores de leitura (`MissionRuntime.get_mission`/`get_state`,
  `WorkflowEngine.get_run`) e, desde a Fase 9, também na mutação
  (`transition()`/`executar_passo()`).
- **Mission Graph** — reconciliador que grava Missões/Decisões/Evidências no
  Knowledge Graph após estado terminal (`learning/mission_reconciliation.py`).
- **Playbooks reais** com composição multi-step ("Auditar Segurança": 6
  checagens + relatório consolidado) e **decision points reais na autoria**
  (`decision_points_template`, Fase 9) — `plan()` real extrai e o
  `DecisionEngine` real escala para humano de verdade, sem monkeypatch nos
  testes (Fase 11).
- **API HTTP** (FastAPI, `src/batman_os/api/`) — ciclo completo de uma
  Missão: submit assíncrono (`POST /missions/security-audit`, `202` +
  `mission_id` imediato via pool de threads dedicado), consulta (`GET
  /jobs/{id}`), resumo após escalada (`POST /missions/{id}/resume`).
  **Autenticação real**: 1 API key estática por tenant, hasheada em repouso
  (SHA-256), via `Authorization: Bearer <chave>` — `tenant_id` nunca mais
  alegado pelo chamador, sempre derivado da chave (Fase 8 + 11).
- **Resiliência a restart**: `Mission.estado` e o `DecisionPoint` pendente de
  uma escalada sobrevivem a um restart do processo (via `EventBus`
  persistido) — `GET /jobs/{id}` continua correto mesmo sob concorrência real
  (Fase 10, com correção de race condition pós-Fase 11).

Ver `README.md` (seção "API HTTP") para como rodar. Ver `docs/spec/` para a
especificação completa (fonte da verdade).

## Backlog — candidatos futuros (nenhum priorizado)

Cada item abaixo tem contexto suficiente para uma sessão futura decidir se
vale a pena, sem precisar reconstruir a investigação do zero.

### 1. `POST /missions/{id}/resume` sobreviver a um restart do processo

**Recusado explicitamente 2× pelo autor** (Fase 10 e Fase 11) — não é
esquecimento, é decisão registrada.

Hoje, se o processo reiniciar entre uma Missão escalar para humano e a
resposta chegar, `GET /jobs/{id}` continua mostrando o `DecisionPoint`
pendente corretamente (Fase 10), mas `POST /resume` ainda falha (`409`)
porque `especificacoes_por_indice` (o mapa de como montar a entrada de cada
step do Playbook) só existe no `JobStore` em memória.

**O que seria necessário**: `ChecagemDeArquivos.entradas_para_regra`
(`orchestration/playbook_step_specs.py`) guarda uma referência de função
(`Callable`), não serializável — precisaria virar uma chave de registro
(`str`) resolvida por um dicionário nome→função (hoje só 2 funções reais
existem: `entradas_para_regra`/`entradas_dependencias_para_regra`, então o
registro seria pequeno na prática). Depois, serializar
`especificacoes_por_indice` via um evento novo no `EventBus`, mesmo padrão
de `PlanCreated`/`HumanEscalationPending`.

**Por que foi recusado**: muda o tipo de um campo já em produção
(`Callable` → `str`), maior blast radius que os outros itens do backlog.

### 2. Timeout/TTL de jobs pendentes em `AwaitingHuman`

Não existe nenhum mecanismo de expiração hoje. `governance/human_review.py::
verificar_sla_e_alarmar()` existe e **alarma** SLA vencido, mas nunca cancela/
força uma decisão default, e está desconectado do fluxo real de escalada
(`orchestration/playbook_driver.py` nunca cria um `HumanReviewRequest`
quando escala). O watchdog (`orchestration/mission_resumption.py::
executar_ciclo_watchdog()`) existe e é testado, mas não tem chamador real
nem endpoint HTTP.

**Por que não foi feito**: sub-feature própria — exige decidir o que
"timeout" FAZ (cancelar a Missão? forçar uma decisão default?), conectar o
watchdog ao fluxo real, e um entry point periódico (cron/endpoint). Maior
que qualquer item já feito nas Fases 10–11.

### 3. Persistência SQLite do `KnowledgeGraph`

**Descartado** (investigação da Fase 9) — não por dificuldade técnica
(seria mecanicamente barato, replica o padrão já usado em `EventBus`), mas
porque **hoje nada em produção alimenta o grafo**: `grafo_conhecimento`
nunca é passado pela CLI real (`cli/batman.py` só tem o subcomando `scan`,
nunca ganhou um subcomando para `auditoria-seguranca`) nem pela API HTTP
(`ColaboradoresCompartilhados` não carrega um grafo). Persistir um grafo que
está sempre vazio em produção resolveria a metade errada do problema.

**Pré-requisito real, se retomado**: primeiro conectar `grafo_conhecimento`
a um caller de produção (CLI ou API) — aí sim a persistência ganha valor.

### 4. Publicar `Decision.evidence` no `EventBus`

**Descartado, obsoleto** — investigação da Fase 9 confirmou que o único
cenário que pareceria justificar isso (Mission Graph via replay de eventos)
já foi resolvido de outra forma desde a Fase 4 (o `Decision` é passado
direto como objeto Python, sem precisar de replay). O cenário que PARECE
próximo (retomar uma Missão após restart durante uma escalada) na verdade
não precisa disso — o `Decision` só nasce DEPOIS da resposta humana; o gap
real ali é o item 1 deste backlog (`especificacoes_por_indice`), não
`Decision.evidence`.

**Não revisitar** sem um caso de uso real e novo que genuinamente precise
de replay de evidência de decisão via EventBus.

### 5. Deploy real do Batman OS (VPS, CI com remoto, produção)

Nunca fez parte do escopo pedido. Hoje o Batman OS é **100% local/
desenvolvimento** — zero `Dockerfile`, zero pipeline de deploy, `.github/
workflows/ci.yml` existe mas só dispara quando o repositório tiver um
remoto real no GitHub (hoje não tem). Diferente do `radar-preditivo`, que
roda em produção real (VPS Hostinger, `exemplo.test`).

Hashing de API key em repouso (Fase 11) já é proporcional a este estado —
revisar quando (e se) houver deploy real: nesse momento, avaliar também
`BATMAN_API_KEYS` em texto puro no `.env` (mesmo tratamento hoje do
`ANTHROPIC_API_KEY`).

### 6. Volumes VIII (Infrastructure) e X (Appendices) da spec

Majoritariamente esboço de topologia física e consolidação — a spec já
documenta que não introduzem componentes de código novos a implementar
(ver nota no `README.md` sobre o Cap.32). Multi-worker/Marketplace/Web UI
(mencionados no Vol.VIII como esboço "v0.1 Draft") nunca tiveram grounding
real — confirmado por investigação direta na Fase 5: zero dependência de
Celery/Redis/RabbitMQ/Kafka/K8s em todo o repositório.

### 7. `tenant_id` real (enforcement, não só campo) em `KnowledgeGraph`

`get_neighbors()`/`impact_analysis()`/`provenance_trail()` não filtram por
tenant — só o campo `tenant_id` foi adicionado a `KnowledgeNode`/
`KnowledgeEdge` (Fase 4). Exclusão deliberada desde então: filtro automático
nesses métodos de travessia fica para quando multi-tenant real usar isso em
produção (mesmo espírito do helper opt-in `foundation/tenant_isolation.py`,
nunca gate obrigatório).

### 8. Migrar os monkeypatches de `plan()` remanescentes (se houver novos)

Os 8 monkeypatches conhecidos até a Fase 11 já foram migrados para Playbooks
reais com `decision_points_template` (zero monkeypatch de `plan()` no
repositório hoje). Se testes futuros de escalada reintroduzirem esse padrão,
preferir declarar o decision point na autoria do Playbook — mecanismo real
desde a Fase 9, não precisa mais de mock.

## O que continua fora de escopo (não é backlog, é decisão permanente)

- **Nenhuma ordem real** — o Batman OS não executa nada (é um scanner de
  governança), isso nunca fez parte do escopo. Diferente do `radar-preditivo`,
  onde ordens reais são a evolução natural do produto (ver `CLAUDE.md`
  daquele repositório).
- **Marketplace/Web UI/Multi-worker** — avaliados e confirmados sem
  grounding real (Fase 5); não são backlog, são "não vale planejar agora".

## Como retomar

Qualquer item deste backlog pode virar uma fase nova seguindo a mesma
disciplina usada nas Fases 1–11: investigar o estado real do código antes
de planejar (nunca assumir), gate `pytest`/`mypy src/`/`ruff check`/`ruff
format --check` verde antes de cada commit, um commit por estágio.
