# ADR-0014 — Defesa em Profundidade para Isolamento de Tenant (RLS Além do Contrato de Aplicação)

| Campo | Valor |
|---|---|
| **Status** | Accepted |
| **Volume** | VIII — Infrastructure |
| **Capítulos relacionados** | 33 (Segurança e Isolamento); Volume III, Cap. 14; ADR-0005 |
| **Princípios invocados** | Full Governance, Zero Cognitive Debt |
| **Data de referência** | v0.1 (Draft) |

## Contexto

A ADR-0005 (Volume III) já obriga `tenantId` estruturalmente em todo dado do Kernel e Runtime, propagado pelo contrato de dados da aplicação. Isso é necessário, mas depende inteiramente da correção do código de aplicação em cada consulta — um único bug (uma query nova, escrita sem o filtro correto) reintroduziria exatamente o risco que a ADR-0005 pretendia eliminar.

## Decisão

O isolamento de tenant é reforçado também na camada de armazenamento, via Row-Level Security (ou partição física equivalente), como defesa em profundidade complementar ao contrato de aplicação já exigido pela ADR-0005 — nunca como substituto dele.

## Alternativas consideradas

1. **Confiar exclusivamente no contrato de aplicação (ADR-0005) como única linha de defesa** — rejeitada: um único bug de código se torna um incidente de vazamento de dado entre tenants, sem nenhuma segunda camada de contenção.
2. **RLS na camada de armazenamento como reforço estrutural, complementar ao contrato de aplicação já exigido** — **decisão aceita**.

## Consequências

**Positivas:**
- Um bug de aplicação que esqueça o filtro de `tenantId` é bloqueado antes de alcançar dados de outro tenant, não apenas detectado após o fato.
- Reduz drasticamente o raio de impacto de erros de programação individuais — consistente com Zero Cognitive Debt: um mesmo tipo de bug não deveria comprometer segurança duas vezes.

**Negativas:**
- Custo de engenharia adicional para configurar e manter políticas de RLS (ou particionamento físico equivalente) em todo armazenamento que carregue `tenantId`.
- Pode introduzir overhead de performance em consultas de alto volume, exigindo tuning cuidadoso conforme a escala do Volume VIII, Cap. 31.

## Conformidade com princípios

| Princípio | Conformidade |
|---|---|
| Full Governance | ✅ Isolamento verificável estruturalmente na infraestrutura, não apenas por convenção de código |
| Zero Cognitive Debt | ✅ Um bug de aplicação não se repete como incidente de segurança — a segunda camada contém o dano |

## Revisão futura

Válida até que o overhead de performance da RLS se prove estruturalmente incompatível com os requisitos de latência de algum `MissionType` de alta frequência — nesse caso, uma ADR futura poderia propor particionamento físico dedicado por tenant como alternativa equivalente em garantia, nunca a remoção da segunda camada de defesa em si.

---

**Voltar:** [Capítulo 33 — Segurança e Isolamento](../03-security-isolation.md)
