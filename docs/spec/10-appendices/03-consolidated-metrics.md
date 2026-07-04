# Capítulo 38 — Métricas e KPIs Consolidados

**Volume:** X — Appendices
**Status da especificação:** v0.1 (Draft)
**Depende de:** Todas as seções "KPIs deste componente" dos 35 capítulos anteriores; Volume VII, Capítulo 30

---

## 38.0 Objetivo do capítulo

Reunir, em uma única referência, todas as métricas definidas capítulo a capítulo ao longo da obra. Este capítulo não substitui o Observability Engine (Volume VII, Cap. 30) — que é o componente que efetivamente calcula e expõe essas métricas em produção — mas serve como o índice de leitura humana que o próprio Cap. 30 pressupõe existir.

## 38.1 As duas métricas mestre

| Métrica | Definição | Fonte primária |
|---|---|---|
| **Cognitive Debt** | Proporção de missões resolvidas autonomamente vs. com apoio humano ou de LLM | Vol. I, Cap. 4, seção 4.9.1; consolidada no Vol. VI, Cap. 26, seção 26.4 |
| **Patrimônio Cognitivo** | Tamanho e profundidade do conjunto acumulado de Knowledge Assets | Vol. I, Cap. 4, seção 4.9.2; medido via Knowledge Graph, Vol. VI, Cap. 23 |

Toda métrica listada abaixo é, em algum grau, um insumo ou uma decomposição de uma dessas duas.

## 38.2 Métricas por volume

### Volume II — Kernel

| Métrica | Capítulo |
|---|---|
| Taxa de missões `Completed` sem `AwaitingHuman`/`AwaitingLLM` | Cap. 6 |
| Tempo médio em cada estado da Missão | Cap. 6 |
| Taxa de `PartiallyFailed` recuperado vs. escalado | Cap. 6 |
| Taxa de planos originados de Playbook vs. composição ad-hoc | Cap. 7 |
| Taxa de `PlanningFailure` | Cap. 7 |
| Distribuição de `resolvedBy` (knowledge/human/llm) | Cap. 8 |
| Taxa de rejeição de respostas de LLM na validação de contrato | Cap. 8 |
| Tempo médio de resposta humana em `AwaitingHuman` | Cap. 8 |
| Taxa de recuperação por tipo de `RecoveryStrategy` | Cap. 9 |
| MTTR interno ao workflow | Cap. 9 |
| Profundidade e latência da fila do Scheduler | Cap. 10 |
| Taxa de eventos consumidos vs. publicados por assinante | Cap. 10 |

### Volume III — Runtime

| Métrica | Capítulo |
|---|---|
| Proporção de Capabilities ativas/deprecated/disabled | Cap. 11 |
| Tempo médio de janela de coexistência de deprecação | Cap. 11 |
| Taxa de sucesso/falha/timeout por Operador | Cap. 12 |
| Taxa de rejeição por violação de `outputSchema` | Cap. 12 |
| Taxa de consultas à Operational Memory por Decision Point | Cap. 13 |
| Número de candidatos a promoção identificados por período | Cap. 13 |
| Latência de despacho por tenant | Cap. 14 |
| Número de incidentes de isolamento de dados | Cap. 14 |

### Volume IV — Capabilities

| Métrica | Capítulo |
|---|---|
| Taxa de Operadores em `Quarantined` | Cap. 15 |
| Tempo médio de certificação de Capability | Cap. 16 |
| Número médio de Capabilities por Skill | Cap. 17 |
| Taxa de abertura de circuit breaker por Tool | Cap. 18 |
| Profundidade média de encadeamento de sub-missões | Cap. 19 |

### Volume V — Workflow Engine

| Métrica | Capítulo |
|---|---|
| Distribuição de missões por criticidade e SLA | Cap. 20 |
| Cobertura de Playbook por `MissionTypeId` | Cap. 21 |
| Número de `PlaybookResolutionAmbiguity` detectados | Cap. 21 |
| Taxa de missões `PartiallyCompleted` vs. `Completed` | Cap. 22 |
| Taxa de acionamento de `fallback-capability` | Cap. 22 |

### Volume VI — Learning Engine

| Métrica | Capítulo |
|---|---|
| Tamanho do Knowledge Graph ao longo do tempo | Cap. 23 |
| Número de regras promovidas por período | Cap. 24 |
| Taxa de concordância média em shadow mode | Cap. 24 |
| Número de propostas de evolução geradas/aprovadas/aplicadas | Cap. 25 |
| Cognitive Debt por `MissionTypeId` (métrica mestre consolidada) | Cap. 26 |

### Volume VII — Governance

| Métrica | Capítulo |
|---|---|
| Número de `GovernanceAlert` por severidade | Cap. 27 |
| Tempo médio de resolução de Human Review por `kind` | Cap. 28 |
| `resolvedByLLMPercentage` por `MissionTypeId` | Cap. 29 |
| Cobertura de métricas consolidadas vs. dispersas | Cap. 30 |

### Volume VIII — Infrastructure

| Métrica | Capítulo |
|---|---|
| Disponibilidade por serviço físico | Cap. 31 |
| Taxa de verificação de integridade de artefato bem-sucedida | Cap. 33 |
| Cobertura de Row-Level Security | Cap. 33 |

## 38.3 Os quatro dashboards do Observability Engine, revisitados

Retomando o Volume VII, Cap. 30, seção 30.3 — cada métrica acima já está mapeada a um dos quatro painéis (`cognitive-debt`, `sla-health`, `learning-throughput`, `governance-backlog`). Este capítulo não redefine esse mapeamento — apenas fornece a lista completa da qual aquele mapeamento parte.

## 38.4 Testes de aceitação

1. **AT-38.1:** Toda métrica listada neste capítulo deve ser reproduzível a partir do Event Bus via `replay`, consistente com AT-30.1 (Volume VII).
2. **AT-38.2:** Nenhuma métrica pode existir neste índice sem uma seção "KPIs deste componente" correspondente em algum capítulo do corpo principal — este capítulo é estritamente consolidação, nunca fonte original.

## 38.5 Status da Implementação

| Já existe | Precisa refatorar | Ainda não existe |
|---|---|---|
| Todas as métricas individuais, especificadas capítulo a capítulo | — | Verificação automatizada de que este índice permanece sincronizado com as fontes à medida que novos capítulos forem adicionados |

---

**Capítulo anterior:** [Capítulo 37 — Índice de ADRs e Anexos](./02-adr-addenda-index.md)
**Próximo capítulo:** [Capítulo 39 — Roadmap de Evolução](./04-evolution-roadmap.md)
