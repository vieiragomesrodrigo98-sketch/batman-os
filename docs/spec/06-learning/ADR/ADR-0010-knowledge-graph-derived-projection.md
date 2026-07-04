# ADR-0010 — Knowledge Graph como Projeção Derivada, Nunca Fonte Primária

| Campo | Valor |
|---|---|
| **Status** | Accepted |
| **Volume** | VI — Learning Engine |
| **Capítulos relacionados** | 23 (Knowledge Graph) |
| **Princípios invocados** | Full Governance, Determinism First |
| **Data de referência** | v0.1 (Draft) |

## Contexto

Um grafo de conhecimento unificado é extremamente útil para consultas de impacto e proveniência (Cap. 23), mas cria um risco arquitetural: se ele passar a ser editável diretamente, ou se componentes do Kernel passarem a consultá-lo como fonte de verdade em tempo real, ele se tornaria uma segunda fonte de verdade paralela aos catálogos já especificados (Capability Registry, Playbook Registry, Rule Registry) — o mesmo erro que a ADR-0003 (Volume II) e a ADR-0004 (Volume III) já rejeitaram em outros contextos.

## Decisão

O Knowledge Graph é estritamente uma **projeção derivada**, reconstruída a partir dos catálogos-fonte e do Event Bus. Nenhuma aresta ou nó é criado diretamente nele — toda mudança de conhecimento passa pelos processos de certificação e governança já especificados nos volumes anteriores, e o grafo é atualizado por reconciliação, não por edição direta. Componentes do Kernel em tempo real (Planning Engine, Decision Engine) consultam os catálogos-fonte diretamente, nunca o Knowledge Graph — que é reservado para análise, auditoria e governança offline (Rule Evolution, Workflow Evolution, Human Review).

## Alternativas consideradas

1. **Knowledge Graph como fonte de verdade única, com catálogos-fonte depreciados** — rejeitada: consolidaria múltiplos processos de certificação distintos (Capability, Playbook, Rule) em uma única estrutura genérica, perdendo as validações específicas de cada tipo de Knowledge Asset já especificadas.
2. **Knowledge Graph editável diretamente para conveniência de análise ad-hoc** — rejeitada: abriria um caminho de mudança de conhecimento sem certificação, violando Full Governance.
3. **Knowledge Graph como projeção derivada, somente leitura, reconciliada periodicamente** — **decisão aceita**.

## Consequências

**Positivas:**
- Consistente com o padrão já estabelecido nas ADRs 0003 e 0004: uma única fonte de verdade por domínio, com projeções derivadas para consultas complementares.
- Kernel em tempo real nunca depende da disponibilidade ou atualidade do Knowledge Graph para decisões críticas — apenas dos catálogos-fonte, mais simples e diretamente acoplados aos processos de certificação.

**Negativas:**
- Introduz uma janela de possível drift entre catálogos-fonte e o grafo (seção 23.7), exigindo reconciliação periódica monitorada.
- Análises de impacto (`impactAnalysis`) podem, teoricamente, estar ligeiramente desatualizadas em relação ao estado mais recente dos catálogos — aceitável para uso em governança e evolução (Cap. 24, 25), mas nunca para decisões do Kernel em tempo real.

## Conformidade com princípios

| Princípio | Conformidade |
|---|---|
| Full Governance | ✅ Nenhuma mudança de conhecimento contorna certificação ao passar pelo grafo |
| Determinism First | ✅ Decisões do Kernel em tempo real permanecem baseadas exclusivamente nos catálogos-fonte certificados |

## Revisão futura

Válida enquanto a janela de reconciliação permanecer dentro de um SLA aceitável para os casos de uso de governança (Rule Evolution, Workflow Evolution). Se o volume de mudanças tornar a reconciliação periódica insuficiente, uma ADR futura pode propor atualização incremental orientada a eventos (consumindo o Event Bus diretamente), preservando a garantia de que o grafo nunca é editado fora desse fluxo derivado.

---

**Voltar:** [Capítulo 23 — Knowledge Graph](../01-knowledge-graph.md)
