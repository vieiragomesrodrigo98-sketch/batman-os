# ADD-0003 — Operational Memory Ativa (Inferência Autônoma)

| Campo | Valor |
|---|---|
| **Status** | **Rejected** — registrado para histórico (Evidence First) |
| **Estende (proposta original)** | Volume III, Capítulo 13 (Operational Memory) |
| **Não altera** | Nenhum capítulo existente. Este anexo documenta uma proposta avaliada e **não incorporada** — o Capítulo 13 e a ADR-0004 permanecem exatamente como especificados |
| **Princípios invocados na avaliação** | Full Governance, Evidence First, Determinism First |

---

## 1. A proposta original

Foi sugerido que a Operational Memory (Vol. III, Cap. 13) deixasse de ser puramente passiva e passasse a **inferir e aplicar** mudanças de comportamento diretamente, com um exemplo concreto:

```
Últimos 200 deploys
  → Falhas
  → Sempre após alteração em X
  → Batman aumenta prioridade
  → Planner muda estratégia
```

A justificativa apresentada foi que isso constitui "inferência determinística", não Machine Learning — e portanto não incorreria no mesmo risco de comportamento probabilístico que a obra rejeita desde a ADR-0001 (Volume I).

## 2. Por que este anexo é registrado como Rejected, não incorporado

A avaliação desta proposta concluiu que ela **já é coberta pela arquitetura existente** — mas com uma diferença estrutural deliberada que não deve ser removida:

O padrão descrito no exemplo ("sempre após alteração em X, deploys falham") é **exatamente** o tipo de sinal que o Capítulo 13 (seção 13.6, `findPromotionCandidates`) e o Capítulo 25 (Workflow Evolution, seção 25.2, "sinais de evolução monitorados") já identificam. A arquitetura já contempla a detecção. A proposta rejeitada é especificamente o passo seguinte: **aplicar** a mudança de estratégia automaticamente, sem o checkpoint de Human Review que a ADR-0004 (Volume III) e a ADR-0011 (Volume VI, shadow mode) exigem.

### 2.1 O argumento "é determinístico, então é seguro" não se sustenta

Um padrão pode ser perfeitamente determinístico na sua detecção (a correlação estatística "sempre após X, falha" é um fato verificável) e ainda assim ser **espúrio ou incompleto** como base causal para uma mudança de comportamento. Determinismo na detecção do padrão não implica corretude da inferência causal por trás dele — e é exatamente esse tipo de erro sutil que Human Review (formalizado no Volume VII) existe para capturar antes que vire regra ativa. A ADR-0004 já nomeia esse risco explicitamente na seção "Alternativas consideradas".

### 2.2 O que a proposta ganharia, e o custo real disso

A proposta ganharia velocidade: a Operational Memory reagiria a um padrão imediatamente, sem esperar o ciclo de Human Review + shadow mode (Vol. VI, Cap. 24). O custo é remover o único ponto do sistema inteiro em que uma mudança de comportamento decisório é revisada por alguém antes de ganhar autoridade — o que, cumulativamente ao longo de centenas de padrões detectados, é precisamente o tipo de erosão de governança que a obra foi desenhada, desde o Capítulo 1, para evitar.

## 3. O que permanece válido da proposta, e onde já está incorporado

- A **detecção** de padrões como o do exemplo já está especificada (Vol. III, Cap. 13, seção 13.6; Vol. V, Cap. 25, seção 25.2).
- A **velocidade** de resposta a padrões de alta confiança é endereçada de forma diferente: a ADR-0011 (Volume VI) já prevê, na seção "Revisão futura", a possibilidade de calibrar o rigor do shadow mode por classe de risco — reduzindo a fricção sem eliminar o checkpoint humano.
- Se, no futuro, houver evidência concreta (não uma ADR, evidência operacional real) de que o gargalo de Human Review está custando mais do que protege, isso deve ser reavaliado através de uma nova proposta que reduza a fricção do processo de revisão — nunca eliminando a revisão em si.

## 4. Status da Implementação

| Já existe | Precisa refatorar | Ainda não existe |
|---|---|---|
| Detecção de padrões (Vol. III, Cap. 13; Vol. V, Cap. 25) | — | N/A — esta proposta específica (aplicação autônoma) não será implementada |

---

**Nota de processo:** este anexo é deliberadamente mantido no repositório, mesmo rejeitado, porque a obra trata rejeição de propostas como um Knowledge Asset em si (Evidence First) — a próxima pessoa que considerar a mesma ideia encontra aqui o raciocínio completo, em vez de reabrir a discussão do zero.
