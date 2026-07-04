# ADR-0006 — Menor Privilégio e Sandboxing Obrigatório para Operadores

| Campo | Valor |
|---|---|
| **Status** | Accepted |
| **Volume** | IV — Capabilities |
| **Capítulos relacionados** | 15 (O que é um Operador) |
| **Princípios invocados** | Full Governance, Zero Cognitive Debt |
| **Data de referência** | v0.1 (Draft) |

## Contexto

Operadores são o ponto de contato do Batman com sistemas reais — produção, dados sensíveis, infraestrutura crítica. Um modelo permissivo por padrão (Operador com acesso amplo, restrito apenas por convenção de uso correto) é o padrão mais comum na indústria, mas historicamente é também a causa mais comum de incidentes de segurança graves quando um Operador tem bug ou é comprometido.

## Decisão

Todo Operador nasce com `allowedActions` vazio (whitelist explícita, nunca blacklist) e uma `SandboxPolicy` obrigatória desde o registro (Cap. 15, seções 15.5–15.6). Nenhuma ação é permitida por omissão. Ações de alto risco (`sideEffectScope: "irreversible-write"`) exigem `requiresApprovalAbove` configurado, conectando estruturalmente o Operador à hierarquia Human Last do Decision Engine (Volume II, Cap. 8).

## Alternativas consideradas

1. **Modelo permissivo por padrão, com blacklist de ações proibidas** — rejeitada: blacklists são estruturalmente incompletas por definição (não é possível enumerar tudo que é proibido de antemão) e historicamente a causa mais comum de escalação de privilégio não intencional.
2. **Whitelist explícita obrigatória + sandboxing obrigatório desde o registro** — **decisão aceita**.

## Consequências

**Positivas:**
- Superfície de dano de um Operador defeituoso ou comprometido é limitada estruturalmente, não apenas por revisão de código.
- Toda ação de alto risco é conectada, por construção, à hierarquia de escalonamento humano já formalizada no Kernel.
- Auditoria de segurança se torna verificação de configuração declarativa, não inspeção manual de cada implementação.

**Negativas:**
- Maior fricção inicial ao registrar um novo Operador — cada ação precisa ser explicitamente listada.
- Operadores legítimos podem falhar por ausência de uma permissão esquecida, exigindo iteração adicional no processo de certificação (Cap. 16).

## Conformidade com princípios

| Princípio | Conformidade |
|---|---|
| Full Governance | ✅ Toda permissão é declarativa e auditável |
| Zero Cognitive Debt | ✅ Incidentes de segurança evitados estruturalmente não geram recorrência de trabalho de investigação manual |

## Revisão futura

Válida enquanto o custo de configuração explícita de permissões for menor que o risco de um modelo permissivo. Uma reversão parcial (ex.: templates de permissão pré-aprovados para classes comuns de Operador, reduzindo fricção sem abrir mão de whitelist) pode ser proposta em ADR futura, desde que preserve o princípio de negação por padrão.

---

**Voltar:** [Capítulo 15 — O que é um Operador](../01-operator.md)
