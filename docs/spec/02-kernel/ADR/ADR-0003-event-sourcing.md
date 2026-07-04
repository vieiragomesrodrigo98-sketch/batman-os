# ADR-0003 — Event Sourcing como Padrão de Auditabilidade do Kernel

| Campo | Valor |
|---|---|
| **Status** | Accepted |
| **Volume** | II — Kernel Architecture |
| **Capítulos relacionados** | 10 (Event Bus & Scheduler) |
| **Princípios invocados** | Full Governance, Evidence First |
| **Data de referência** | v0.1 (Draft) |

## Contexto

Full Governance (Princípio 9) exige que toda decisão do Batman seja auditável — quem/o quê decidiu, com base em quê, e quando. Um modelo de persistência que armazena apenas o estado final de uma Missão (ex.: uma linha de banco de dados atualizada em `UPDATE`) perde a trilha causal de como aquele estado foi alcançado.

## Decisão

O Kernel adota **event sourcing** como padrão arquitetural transversal: o Event Bus (Cap. 10) é um log imutável, append-only, e o estado de qualquer Missão, Plano, Decisão ou WorkflowRun é, por definição, derivável a partir da sequência de eventos publicados — nunca a fonte primária de verdade em si mesma.

## Alternativas consideradas

1. **Persistência de estado mutável (CRUD tradicional) com log de auditoria separado e best-effort** — rejeitada: cria duas fontes de verdade que podem divergir; o log de auditoria vira "nice to have" em vez de mecanismo estrutural, violando Full Governance.
2. **Event sourcing como padrão único de verdade, com views materializadas para consulta rápida** — **decisão aceita**.

## Consequências

**Positivas:**
- `replay(missionId)` (AT-10.1) é sempre possível e sempre consistente, porque não existe estado "além" dos eventos.
- Depuração de incidentes se torna reconstrução determinística da história, não inspeção de um snapshot final sem contexto.
- Learning Engine (Volume VI) e Governance Engine (Volume VII) podem consumir o mesmo stream de eventos sem acoplamento direto ao Kernel.

**Negativas:**
- Views materializadas (para consulta eficiente de "estado atual") precisam ser mantidas e reconciliadas contra o log de eventos — complexidade operacional adicional.
- Crescimento não limitado do log de eventos exige estratégia de arquivamento/particionamento (a especificar no Volume VIII — Infrastructure).

## Conformidade com princípios

| Princípio | Conformidade |
|---|---|
| Full Governance | ✅ Motivação direta desta ADR |
| Evidence First | ✅ Toda `Decision` e transição de estado carrega evidência rastreável no próprio evento que a registra |

## Revisão futura

Válida até que uma ADR futura demonstre, com evidência de custo operacional real (ex.: volume de eventos inviabilizando replay em tempo hábil para missões críticas), a necessidade de um modelo híbrido com snapshotting periódico — o que, se adotado, deve preservar a garantia de que o snapshot é sempre reconstruível a partir do log, nunca uma fonte de verdade paralela e divergente.

---

**Voltar:** [Capítulo 10 — Event Bus & Scheduler](../06-event-bus-scheduler.md)
