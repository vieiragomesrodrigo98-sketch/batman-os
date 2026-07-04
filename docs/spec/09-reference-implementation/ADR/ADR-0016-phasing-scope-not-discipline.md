# ADR-0016 — Faseamento da Implementação Reduz Escopo, Nunca Disciplina

| Campo | Valor |
|---|---|
| **Status** | Accepted |
| **Volume** | IX — Reference Implementation |
| **Capítulos relacionados** | 34 (Implementação de Referência) |
| **Princípios invocados** | Full Governance, Evidence First, Determinism First |
| **Data de referência** | v0.1 (Draft) |

## Contexto

Uma especificação deste tamanho cria uma tentação natural de implementação: "vamos construir um MVP sem toda a burocracia de certificação e revisão, e adicionar isso depois, quando o sistema já estiver provando valor". Esse padrão é comum na indústria e quase sempre resulta em uma dívida de governança que nunca é paga — o sistema cresce em torno da ausência de disciplina, e retrofitting se torna progressivamente mais custoso e mais resistido politicamente ("já funciona, para que mudar").

## Decisão

O roteiro de bootstrap (Cap. 34) permite reduzir **escopo** (menos Capabilities, um único tenant, ausência de LLM ou de Learning Engine nas fases iniciais) mas nunca permite reduzir **disciplina** (Evidence First, Full Governance, separação de camadas da ADR-0002). Mesmo o Walking Skeleton da Fase 0 já carrega `tenantId` em todo dado, já separa Planning de Decision de Execution, e já exige evidência em toda decisão.

## Alternativas consideradas

1. **MVP sem certificação nem auditoria, adicionadas em uma fase posterior** — rejeitada: historicamente, este padrão resulta em dívida de governança que nunca é integralmente paga, e o sistema em produção passa a operar permanentemente fora do que a própria especificação exige.
2. **Faseamento por redução de escopo funcional, com disciplina arquitetural presente desde a Fase 0** — **decisão aceita**.

## Consequências

**Positivas:**
- A Fase 0, por menor que seja em capacidade, já é auditável, determinística e governada — não existe um período de "dívida arquitetural planejada" a ser paga depois.
- Decisões de arquitetura fundamentais (separação de camadas, event sourcing, tenantId obrigatório) nunca precisam de uma reescrita estrutural posterior — apenas de extensão de escopo.

**Negativas:**
- A Fase 0 é mais cara de construir do que um protótipo descartável equivalente sem essas garantias — o tempo até o primeiro valor demonstrável é maior.
- Exige disciplina de equipe desde o primeiro commit, o que pode ser culturalmente mais difícil de sustentar sob pressão de prazo do que "vamos arrumar isso depois".

## Conformidade com princípios

| Princípio | Conformidade |
|---|---|
| Full Governance | ✅ Nenhuma fase, por menor que seja, opera fora de auditoria |
| Evidence First | ✅ Presente desde a Fase 0, não introduzida posteriormente |
| Determinism First | ✅ A separação de camadas (ADR-0002) é estrutural desde o primeiro código escrito |

## Revisão futura

Válida como princípio permanente de qualquer expansão futura da implementação de referência. Não há cenário legítimo, dentro desta especificação, em que "reduzir disciplina temporariamente" seja uma decisão aceitável — apenas redução de escopo funcional é uma variável de negociação válida.

---

**Voltar:** [Capítulo 34 — Implementação de Referência do Batman OS](../01-reference-implementation.md)
