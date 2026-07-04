# ADR-0015 — Verificação de Integridade de Artefato como Bloqueio Obrigatório de Execução

| Campo | Valor |
|---|---|
| **Status** | Accepted |
| **Volume** | VIII — Infrastructure |
| **Capítulos relacionados** | 33 (Segurança e Isolamento, seção 33.5); Volume IV, Cap. 16 |
| **Princípios invocados** | Full Governance, Determinism First |

---

## Contexto

O pipeline de certificação de Capability (Volume IV, Cap. 16) garante que um artefato satisfaz o checklist de qualidade e segurança **no momento da certificação**. Sem um mecanismo de verificação de integridade em tempo de execução, nada impede que o artefato efetivamente carregado em produção — por erro de deployment, ou por adulteração maliciosa — seja diferente daquele que foi certificado, invalidando silenciosamente toda a disciplina de certificação já especificada.

## Decisão

O Execution Engine (Volume III, Cap. 12) verifica, antes de toda invocação de Operador, que o hash do artefato em produção corresponde exatamente ao hash certificado (`SupplyChainIntegrity.verify()`, Cap. 33, seção 33.5). Uma divergência bloqueia a invocação e coloca o Operador em `Quarantined` imediatamente, tratada com a mesma severidade de uma violação de permissão (Volume IV, Cap. 15, seção 15.8).

## Alternativas consideradas

1. **Confiar no processo de deployment como suficientemente controlado, sem verificação em runtime** — rejeitada: depende de disciplina de processo externo ao próprio sistema, sem verificação estrutural — o mesmo tipo de lacuna que a obra rejeitou repetidamente (ex.: ADR-0006, menor privilégio ao invés de confiança em disciplina).
2. **Verificação de integridade obrigatória antes de toda invocação, com bloqueio automático em caso de divergência** — **decisão aceita**.

## Consequências

**Positivas:**
- A garantia de que "o que roda em produção é o que foi certificado" deixa de depender de confiança no processo de deployment e passa a ser verificável e enforced automaticamente.
- Fecha uma lacuna de segurança de cadeia de suprimentos que nenhum capítulo anterior cobria explicitamente.

**Negativas:**
- Adiciona uma verificação de hash a cada invocação — custo de performance marginal, mas não nulo, especialmente para Operadores de alta frequência.
- Exige infraestrutura de assinatura/hash de artefato integrada ao pipeline de certificação (Volume IV, Cap. 16), que precisa ser mantida com o mesmo rigor que os próprios testes de aceitação.

## Conformidade com princípios

| Princípio | Conformidade |
|---|---|
| Full Governance | ✅ Nenhum artefato executa sem prova verificável de que corresponde ao que foi certificado |
| Determinism First | ✅ Reforça que o comportamento de uma Capability em produção é, por construção, idêntico ao que foi validado na certificação — nenhuma divergência silenciosa é possível |

## Revisão futura

Válida indefinidamente como controle de segurança de linha de base. Uma ADR futura poderia refinar a frequência de verificação (por invocação vs. por período, para Operadores de altíssima frequência onde o custo por invocação se torne proibitivo), mas nunca eliminar a verificação em si sem um mecanismo equivalente de garantia de integridade.

---

**Voltar:** [Capítulo 33 — Segurança e Isolamento](../03-security-isolation.md)
