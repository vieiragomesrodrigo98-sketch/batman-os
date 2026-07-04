# ADR-0001 — Batman será um Sistema Cognitivo Determinístico

| Campo | Valor |
|---|---|
| **Status** | Accepted |
| **Volume** | I — Foundation |
| **Capítulos relacionados** | 1 (O Problema), 2 (Filosofia), 3 (Princípios) |
| **Princípios invocados** | Determinism First, LLM Last, Full Governance |
| **Data de referência** | v0.1 (Draft) |

## Contexto

Modelos de linguagem probabilísticos, quando usados como núcleo de raciocínio de um agente, introduzem três propriedades indesejáveis para engenharia crítica: custo variável por execução, comportamento não determinístico entre execuções idênticas, e baixa auditabilidade da cadeia decisória (ver Capítulo 1, seções 1.2.1–1.2.3).

## Decisão

O Batman utilizará mecanismos determinísticos (regras, Capabilities catalogadas, Workflows explícitos) como padrão de operação. Modelos de linguagem serão tratados como **componentes externos e periféricos**, isolados por contratos determinísticos de entrada e saída, e nunca ocuparão a posição de componente central de decisão do sistema.

## Alternativas consideradas

1. **Núcleo baseado em LLM com regras como camada de suporte** — rejeitada por inverter a hierarquia definida no Princípio 6 (LLM Last) e comprometer Determinism First de forma estrutural, não periférica.
2. **Sistema puramente baseado em regras, sem qualquer uso de LLM** — rejeitada por eliminar o mecanismo de aquisição de novo conhecimento para casos não cobertos (violaria Learn Forever e Human Last/LLM Last como hierarquia de escalonamento).
3. **Sistema híbrido com LLM como componente periférico e determinístico como núcleo** — **decisão aceita**.

## Consequências

**Positivas:**
- Previsibilidade de comportamento e custo.
- Auditabilidade completa da cadeia decisória (suporta Full Governance).
- Repetibilidade: mesma entrada, mesma saída, em qualquer momento.
- Baixo custo operacional em regime de maturidade (conforme Cognitive Debt converge para zero).

**Negativas:**
- Maior esforço de engenharia inicial — construir Capabilities e regras é mais caro upfront do que delegar a um LLM.
- Maior investimento inicial de capital de engenharia antes de o sistema atingir cobertura útil.
- Curva de aprendizado incremental: o sistema começa com Cognitive Debt alto e depende de disciplina de captura de conhecimento (Learn Forever) para evoluir.

## Conformidade com princípios (Capítulo 3)

| Princípio | Conformidade |
|---|---|
| 1. Knowledge First | ✅ Reforçada — a decisão prioriza estruturas de conhecimento persistentes sobre respostas ad-hoc |
| 2. Determinism First | ✅ É a motivação direta desta ADR |
| 6. LLM Last | ✅ Formalizada como consequência arquitetural direta |
| 9. Full Governance | ✅ Reforçada — determinismo é pré-condição de auditabilidade completa |

## Revisão futura

Esta ADR permanece válida até que uma nova ADR demonstre, com evidência (Princípio 3, Evidence First), que a hierarquia determinístico-primeiro deixou de ser adequada para alguma classe específica de Missão — nesse caso, a excepcionalidade deve ser escopada e documentada, nunca aplicada como mudança silenciosa de comportamento padrão.

---

**Voltar:** [Capítulo 4 — Definições Oficiais](../04-terminology.md)
