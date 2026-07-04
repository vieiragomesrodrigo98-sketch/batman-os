# ADR-0002 — Separação Estrita entre Planning, Decision e Execution

| Campo | Valor |
|---|---|
| **Status** | Accepted |
| **Volume** | II — Kernel Architecture |
| **Capítulos relacionados** | 7 (Planning Engine), 8 (Decision Engine), 9 (Workflow Engine) |
| **Princípios invocados** | Determinism First, Evidence First, Evolution Never Stops |
| **Data de referência** | v0.1 (Draft) |

## Contexto

Uma alternativa de design comum em frameworks de agentes é unificar planejamento, decisão e execução em um único ciclo ("agent loop"), tipicamente centrado em um LLM que decide passo a passo o que fazer a seguir. Essa abordagem é flexível, mas impede auditoria determinística: não é possível separar "qual era o plano" de "qual decisão foi tomada em qual ponto", porque ambos emergem da mesma chamada de raciocínio.

## Decisão

O Kernel do Batman OS separa estritamente três responsabilidades em componentes distintos, com contratos de dados explícitos entre eles:

1. **Planning Engine** (Cap. 7) — determina apenas a estrutura (quais passos, em qual ordem, com quais dependências), sem resolver nenhuma ambiguidade de conteúdo.
2. **Decision Engine** (Cap. 8) — resolve exclusivamente os `DecisionPoint`s explicitados pelo plano, aplicando a hierarquia Knowledge → Human → LLM.
3. **Workflow Engine** (Cap. 9) — executa o plano já decidido, sem reabrir decisões estruturais (exceto via `escalate`, que devolve explicitamente ao Decision Engine).

## Alternativas consideradas

1. **Agent loop unificado (planejar-decidir-executar em uma única chamada por passo)** — rejeitada: impossibilita replay determinístico (AT-7.1) e auditoria de "por que esta decisão" isolada de "por que este passo existe".
2. **Planning e Decision unificados, Execution separado** — rejeitada: um plano precisa ser auditável e reutilizável (via Playbook) independentemente das decisões concretas tomadas em uma execução específica; unificá-los acopla estrutura a conteúdo.
3. **Três componentes estritamente separados com contratos de dados explícitos** — **decisão aceita**.

## Consequências

**Positivas:**
- Um mesmo `ExecutionPlan` pode ser auditado, testado e reutilizado (via Playbook) independentemente de quais decisões específicas foram tomadas em cada execução.
- Testes de replay determinístico (AT-7.1) tornam-se possíveis porque cada camada tem contrato de entrada/saída isolado.
- Falhas podem ser atribuídas com precisão a uma camada específica (estrutura malformada vs. decisão errada vs. falha operacional).

**Negativas:**
- Maior número de componentes e contratos de dados a manter.
- Cenários que "naturalmente" misturariam planejamento e decisão (ex.: um LLM sugerindo tanto a estrutura quanto o conteúdo de um passo) exigem desenho explícito de como essa sugestão é decomposta nas três camadas — não pode ser aceita como um bloco monolítico.

## Conformidade com princípios

| Princípio | Conformidade |
|---|---|
| Determinism First | ✅ Motivação direta — replay determinístico de planos (AT-7.1) só é possível com esta separação |
| Evidence First | ✅ Cada `Decision` carrega evidência isolada da estrutura do plano que a originou |
| Evolution Never Stops | ✅ Novos tipos de missão podem introduzir novos Playbooks (estrutura) sem alterar a lógica do Decision Engine, e vice-versa |

## Revisão futura

Esta ADR permanece válida enquanto o custo de manter três contratos separados for menor que o custo de auditoria perdida em uma abordagem unificada. Uma reversão exigiria evidência concreta de que a separação está gerando gargalo de engenharia desproporcional ao ganho de auditabilidade — o que, dado o diagnóstico do Capítulo 1, é considerado improvável no horizonte desta especificação.

---

**Voltar:** [Capítulo 10 — Event Bus & Scheduler](../06-event-bus-scheduler.md)
