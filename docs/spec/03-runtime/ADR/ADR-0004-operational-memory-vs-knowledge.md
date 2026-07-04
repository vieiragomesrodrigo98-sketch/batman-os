# ADR-0004 — Operational Memory Não É Fonte de Verdade Comportamental

| Campo | Valor |
|---|---|
| **Status** | Accepted |
| **Volume** | III — Runtime |
| **Capítulos relacionados** | 13 (Operational Memory) |
| **Princípios invocados** | Full Governance, Zero Cognitive Debt, Determinism First |
| **Data de referência** | v0.1 (Draft) |

## Contexto

Um padrão comum em sistemas que registram histórico de execuções é permitir que esse histórico influencie diretamente o comportamento futuro do sistema — por exemplo, "se aconteceu assim nas últimas 10 vezes, faça assim de novo automaticamente". Isso é tentador para reduzir Cognitive Debt rapidamente, mas cria um caminho de mudança de comportamento não governado: o sistema passaria a "aprender" sem revisão explícita, minando Full Governance.

## Decisão

A Operational Memory (Cap. 13) é estritamente uma camada de consulta histórica, consumida como **evidência** pelo Decision Engine (cálculo de confiança) e como **matéria-prima de candidatos** para o Learning Engine (Volume VI). Ela nunca altera diretamente uma regra, Capability ou Playbook. Toda promoção de um padrão observado a conhecimento ativo passa obrigatoriamente por Human Review (Volume VII), mesmo quando o padrão é estatisticamente muito consistente.

## Alternativas consideradas

1. **Auto-promoção de padrões frequentes e consistentes a regras ativas** — rejeitada: viola Full Governance (Princípio 9) ao introduzir mudança de comportamento sem trilha de aprovação explícita, e cria risco de reforçar vieses ou correlações espúrias sem revisão.
2. **Operational Memory como camada puramente passiva de evidência e geração de candidatos, com promoção sempre humana** — **decisão aceita**.

## Consequências

**Positivas:**
- Toda mudança de comportamento do sistema permanece rastreável a uma decisão humana explícita de promoção (Learning Engine, Volume VI).
- Reduz risco de "regras fantasmas" emergindo de correlações espúrias no histórico operacional.
- Mantém a garantia de Determinism First: o comportamento do Kernel em um dado momento depende apenas do estado explícito e versionado da Knowledge Base, nunca de uma média móvel implícita de execuções recentes.

**Negativas:**
- Redução de Cognitive Debt é mais lenta do que seria com auto-promoção — exige capacidade de revisão humana como gargalo deliberado.
- Requer processo maduro de Human Review (Volume VII) para não acumular um backlog de candidatos nunca revisados, o que anularia o benefício prático desta camada.

## Conformidade com princípios

| Princípio | Conformidade |
|---|---|
| Full Governance | ✅ Motivação direta — nenhuma mudança de comportamento sem aprovação rastreável |
| Determinism First | ✅ Comportamento do Kernel nunca depende implicitamente de histórico recente não promovido |
| Zero Cognitive Debt | ⚠️ Trade-off explícito — a métrica melhora mais devagar, mas com integridade de governança preservada |

## Revisão futura

Uma futura ADR poderia introduzir promoção semi-automática para classes de decisão de baixo impacto e alta reversibilidade (ver Volume II, Cap. 8, seção 8.4, sobre reversibilidade), desde que mantenha um mecanismo de aprovação assíncrona auditável — nunca aplicação imediata sem qualquer checkpoint humano.

---

**Voltar:** [Capítulo 13 — Operational Memory](../03-operational-memory.md)
