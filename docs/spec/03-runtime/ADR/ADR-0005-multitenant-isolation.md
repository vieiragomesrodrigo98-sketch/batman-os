# ADR-0005 — Isolamento Multi-Tenant como Propriedade Estrutural, não Opcional

| Campo | Valor |
|---|---|
| **Status** | Accepted |
| **Volume** | III — Runtime |
| **Capítulos relacionados** | 14 (Concorrência e Isolamento de Missões) |
| **Princípios invocados** | Full Governance, Mission Driven |
| **Data de referência** | v0.1 (Draft) |

## Contexto

O Batman OS é desenhado para operar em contextos onde múltiplas áreas de negócio, produtos ou clientes (ex.: o padrão observado em iniciativas como MOK-VIBE, com múltiplos parceiros e pacotes de serviço) compartilham a mesma instância do sistema. Sem isolamento estrutural desde o Kernel, cada novo caso de uso multi-tenant exigiria retrofitting de segurança e fairness — um padrão historicamente propenso a vazamento de dados entre tenants e degradação de serviço por vizinhos ruidosos ("noisy neighbor").

## Decisão

`tenantId` é um campo obrigatório e propagado estruturalmente por toda a cadeia de dados do Kernel e Runtime — `Mission`, `ExecutionPlan`, `WorkflowRun`, `OperationalRecord` e `KernelEvent` (Cap. 14, seção 14.3). Nenhuma entidade pode ser processada sem esse campo. Fairness entre tenants é implementada como extensão explícita do Scheduler (weighted round-robin com quotas configuráveis), não como comportamento emergente da fila de prioridade simples.

## Alternativas consideradas

1. **Isolamento por instância física separada por tenant** — rejeitada como padrão default: custo operacional linear com número de tenants, incompatível com Evolution Never Stops em cenários de multi-tenancy de alto volume; permanece uma opção válida para tenants que exigem isolamento físico regulatório, mas como exceção configurável, não como arquitetura padrão.
2. **`tenantId` como convenção de aplicação, não como campo estrutural do Kernel** — rejeitada: convenções não impostas pelo Kernel são historicamente a causa mais comum de vazamento de dado entre tenants (campo esquecido em uma nova query).
3. **`tenantId` obrigatório e estruturalmente propagado, com fairness explícita no Scheduler** — **decisão aceita**.

## Consequências

**Positivas:**
- Isolamento de dados torna-se uma propriedade verificável estruturalmente (AT-14.1), não uma disciplina de código a se manter por convenção.
- KPIs de governança (Cognitive Debt, Patrimônio Cognitivo) podem ser segmentados por tenant desde o primeiro dia, sem retrofitting.
- Fairness explícita previne degradação silenciosa de tenants de menor volume.

**Negativas:**
- Todo componente novo do Kernel ou Runtime precisa nascer com suporte a `tenantId` — aumenta a superfície mínima de qualquer nova funcionalidade.
- Configuração de quotas de fairness exige manutenção contínua por parte da Governance (Volume VII), não é "configure uma vez e esqueça".

## Conformidade com princípios

| Princípio | Conformidade |
|---|---|
| Full Governance | ✅ Isolamento estrutural é pré-condição para auditoria confiável por tenant |
| Mission Driven | ✅ Reforça que toda Missão existe em um contexto explícito (tenant + intenção), nunca solta |

## Revisão futura

Válida até que surja um caso de uso legítimo exigindo isolamento físico obrigatório (ex.: exigência regulatória específica de um parceiro) — nesse caso, uma ADR subsequente deve especificar o mecanismo de provisionamento de instância dedicada como extensão explícita deste modelo, não como substituição dele.

---

**Voltar:** [Capítulo 14 — Concorrência e Isolamento de Missões](../04-concurrency-isolation.md)
