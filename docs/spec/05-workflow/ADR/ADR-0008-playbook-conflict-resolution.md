# ADR-0008 — Resolução Determinística de Conflito entre Playbooks

| Campo | Valor |
|---|---|
| **Status** | Accepted |
| **Volume** | V — Workflow Engine |
| **Capítulos relacionados** | 21 (Playbooks) |
| **Princípios invocados** | Determinism First, Full Governance |
| **Data de referência** | v0.1 (Draft) |

## Contexto

À medida que o catálogo de Playbooks cresce (Evolution Never Stops), é inevitável que múltiplos Playbooks eventualmente casem estruturalmente com o mesmo `MissionIntent`. Uma resolução implícita (ex.: "o primeiro encontrado na busca", "o mais recentemente registrado") introduziria não-determinismo dependente de detalhes de implementação do registro, não de decisão arquitetural deliberada.

## Decisão

A resolução de Playbooks concorrentes segue uma cadeia estrita e determinística de critérios (Cap. 21, seção 21.4): prioridade explícita → especificidade do matcher → versão SemVer mais recente. Um empate real após todos os critérios é tratado como erro de configuração (`PlaybookResolutionAmbiguity`), nunca resolvido silenciosamente.

## Alternativas consideradas

1. **Resolução por ordem de registro ("primeiro a chegar")** — rejeitada: acopla comportamento a um detalhe operacional (ordem de deploy/registro) sem relação com a intenção de negócio, e é frágil a reordenações incidentais do catálogo.
2. **Resolução por heurística de similaridade semântica (ex.: embedding de texto do intent)** — rejeitada: introduz não-determinismo e depende de um componente probabilístico exatamente no ponto que deveria ser mais determinístico do Kernel, violando a ADR-0001 (Volume I).
3. **Cadeia estrita de critérios estruturais com falha explícita em caso de empate real** — **decisão aceita**.

## Consequências

**Positivas:**
- Qualquer resultado de resolução de Playbook é explicável e reproduzível por auditoria (basta reaplicar a cadeia de critérios).
- Empates reais são forçosamente corrigidos na origem (prioridade ou especificidade do catálogo), prevenindo acúmulo de ambiguidade "resolvida" de forma inconsistente ao longo do tempo.

**Negativas:**
- Exige disciplina de configuração de prioridade por parte de quem registra novos Playbooks — não é "automático" no sentido de nunca exigir intervenção humana.
- Certificação de novos Playbooks (Cap. 21, seção 21.6) precisa incluir verificação de ambiguidade contra todo o catálogo ativo, adicionando custo ao pipeline de certificação.

## Conformidade com princípios

| Princípio | Conformidade |
|---|---|
| Determinism First | ✅ Motivação direta desta ADR |
| Full Governance | ✅ Toda resolução é auditável e reproduzível a partir de critérios declarados |

## Revisão futura

Válida enquanto o volume de Playbooks não tornar a verificação de ambiguidade computacionalmente inviável em tempo de certificação — nesse caso, uma ADR futura pode introduzir particionamento do catálogo por `missionTypeId` com verificação escopada, preservando a garantia de determinismo dentro de cada partição.

---

**Voltar:** [Capítulo 21 — Playbooks](../02-playbooks.md)
