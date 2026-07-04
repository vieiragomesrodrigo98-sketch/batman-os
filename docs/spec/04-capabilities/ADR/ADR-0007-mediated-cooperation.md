# ADR-0007 — Cooperação Mediada como Único Padrão de Comunicação entre Operadores

| Campo | Valor |
|---|---|
| **Status** | Accepted |
| **Volume** | IV — Capabilities |
| **Capítulos relacionados** | 19 (Cooperação entre Operadores) |
| **Princípios invocados** | Full Governance, Determinism First, Mission Driven |
| **Data de referência** | v0.1 (Draft) |

## Contexto

Muitos frameworks de agentes multi-agente permitem comunicação direta entre agentes (ex.: um agente "chama" outro agente como uma sub-rotina, trocando mensagens diretamente). Isso é flexível, mas cria um caminho de dado que não passa pelo Event Bus (Volume II, Cap. 10), quebrando a garantia de que todo estado do sistema é reconstruível via `replay`.

## Decisão

Nenhum Operador recebe, em tempo de execução, referência a outro Operador. Toda cooperação passa pelo Workflow Engine (Volume II, Cap. 9), seja via grafo de dependências de um mesmo `ExecutionPlan` (pipeline, fan-out/fan-in), seja via criação de sub-missão governada (Cap. 19, seção 19.3.3).

## Alternativas consideradas

1. **Comunicação direta Operador-a-Operador (message passing peer-to-peer)** — rejeitada: cria um caminho de dado auditável apenas se cada implementação de Operador decidir, por conta própria, publicar eventos equivalentes — uma garantia frágil e não estrutural.
2. **Toda cooperação mediada pelo Workflow Engine, com sub-missão como único mecanismo de delegação de trabalho independente** — **decisão aceita**.

## Consequências

**Positivas:**
- Toda passagem de dado entre Operadores é, por construção, um evento auditável no Event Bus.
- Sub-missões preservam contabilização independente de Cognitive Debt e isolamento de tenant (Volume III, Cap. 14), evitando "trabalho invisível".
- Testabilidade: um Operador pode ser testado isoladamente, pois seu contrato de entrada/saída nunca inclui referências a outros Operadores.

**Negativas:**
- Padrões de cooperação mais complexos (ex.: negociação iterativa entre dois Operadores) exigem modelagem explícita como múltiplos passos de workflow ou sub-missões, o que pode ser mais verboso do que uma troca de mensagens direta.
- Latência adicional em cenários de cooperação intensa, por passar sempre pela camada de orquestração do Kernel.

## Conformidade com princípios

| Princípio | Conformidade |
|---|---|
| Full Governance | ✅ Motivação direta desta ADR |
| Determinism First | ✅ Ordem e roteamento de cooperação são decididos pelo `ExecutionPlan`, não por lógica ad-hoc dentro de um Operador |
| Mission Driven | ✅ Trabalho delegado é sempre modelado como sub-missão, nunca como chamada solta fora do contexto de missão |

## Revisão futura

Válida até que surja um caso de uso com requisito de latência incompatível com a camada de orquestração — nesse caso, uma ADR futura deve especificar um mecanismo de "fast path" auditável (ex.: eventos publicados de forma assíncrona após a interação, mantendo rastreabilidade), nunca comunicação direta sem qualquer registro.

---

**Voltar:** [Capítulo 19 — Cooperação entre Operadores](../05-cooperation.md)
