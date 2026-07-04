# Batman OS

**Construindo um Sistema Operacional Cognitivo Determinístico Autônomo**

> "Um sistema inteligente não é aquele que responde todas as perguntas. É aquele que
> reduz continuamente a quantidade de perguntas que precisam ser feitas."

Este repositório é a **implementação de referência** do Batman OS, cuja especificação
de arquitetura completa vive em [`docs/spec/`](docs/spec/README.md). O Batman OS é a
evolução natural do Batman em `radar-preditivo/Batman/` (270 regras de governança,
46 agentes, ledger, patrulha, sweep) — desacoplado para poder operar em outros
projetos, sem perder nada do que já funciona.

**Regra de ouro** (herdada da especificação): sempre que houver divergência entre o
código deste repositório e `docs/spec/`, a especificação vence, até que uma nova ADR
aprove formalmente a mudança.

## Estado

**Especificação completa: 39 capítulos, 10 volumes, 17 ADRs, 6 Anexos** (Volumes
I–X). **Código: núcleo funcional completo (Volumes I–VII)** — Foundation, Kernel
Architecture, Runtime, Capabilities, Workflow Engine, Learning Engine, Governance —
30 capítulos (Cap.4/6-30), 291 testes cobrindo todos os `AT-X.Y` da própria
especificação, `mypy`/`ruff` limpos. Ver `docs/spec/SUMMARY.md` para o índice
completo. Inclui também o cenário de referência ponta a ponta do Vol.IX Cap.35
(`tests/reference/`), provando que o sistema se compõe através de 5 volumes
diferentes, não só capítulo a capítulo. Volumes VIII (Infrastructure) e X
(Appendices) são volumes de topologia física e consolidação — não introduzem
componentes de código novos a implementar (ver nota sobre o Cap.32 abaixo).

Migração das 270 regras do Batman atual (`radar-preditivo/Batman/`) para
Capabilities/Operadores reais é trabalho futuro, deliberadamente fora desta
primeira rodada — ver `docs/governanca/BATMAN_BACKLOG.md` no repositório
`radar-preditivo` para o backlog de pendências dessa migração.

## Estrutura

```
docs/spec/          # especificação completa (fonte da verdade — só leitura para o código)
src/batman_os/
  foundation/        # Vol. I — tipos oficiais do glossário (Mission, Capability, etc.)
  kernel/            # Vol. II — Mission Runtime, Planning/Decision/Workflow Engine, Event Bus, Scheduler
  runtime/           # Vol. III — Capability Engine, Execution Engine, Operational Memory, Concorrência
  capabilities/      # Vol. IV — Operator, certificação de Capability, Skills, Tools, Cooperação
  workflow/          # Vol. V — Missões formais, Playbooks, Recuperação/Fallback
  learning/          # Vol. VI — Knowledge Graph, Rule/Workflow Evolution, Operational Learning
  governance/        # Vol. VII — Governance Engine, Human Review, LLM Escalation, Observability Engine
tests/               # 1 arquivo de teste por capítulo, nomeado pelos próprios AT-X.Y da spec
```

**Nota sobre o Volume VIII, Cap.32 (Estrutura de Diretórios):** aquele capítulo
propõe pastas de topo kebab-case (`kernel/`, `runtime/`, `workflow/`, `learning/`,
`governance/`, `shared/`, uma subpasta por capítulo). Decisão do autor (2026-07-04):
manter a estrutura acima como a **tradução Python** desse mapeamento — mesmo
componente lógico → mesmo local, adaptado ao empacotamento idiomático da linguagem
(`src/<pacote>/`, arquivos `snake_case.py`, já que nomes kebab-case não são
identificadores Python válidos), o mesmo raciocínio já aplicado ao pseudocódigo
TypeScript-like da spec. `foundation/` cumpre o papel que o Cap.32 chama de
`shared/`. Isso não é dívida a resolver — é a mesma "regra de ouro" (spec vence)
aplicada com bom senso de tradução de convenção, não de estrutura.

## Convenção de nomenclatura

O vocabulário oficial do Kernel (`Mission`, `Capability`, `Skill`, `Operator`,
`Workflow`, `Playbook`, `Knowledge Asset`, `Decision`, `Event`) segue exatamente a
definição do Volume I, Capítulo 4 — **não pode ser usado com outro sentido em
nenhum lugar do código** (a própria especificação trata divergência de nomenclatura
como dívida técnica, não sinônimo válido).

Ao redor desse núcleo, por decisão do autor, a nomenclatura já usada no Batman
atual é preservada o máximo possível:

| Termo oficial da spec (imutável) | Nomenclatura do Batman atual preservada como... |
|---|---|
| `Mission`, `Capability`, `Skill`, `Operator`, `Workflow`, `Playbook`, `Knowledge Asset`, `Decision`, `Event` | — núcleo do Kernel, fixado pelo Cap.4 |
| — | CLI continua `batman`, mesmos subcomandos (`scan`, `patrol`, `sweep`, `fp`, `agents`, `init`) |
| — | **"Alfred"** — nome do Operador/Capability de relatório e observabilidade |
| — | **"Robin"** — nome do Operador dinâmico que roda testes de verdade |
| — | Os **46 "agentes"** atuais (`sre`, `security_engineer`, `ai_engineer`, `vps_infra`, `ethical_hacker`, `red_team`, ...) viram os nomes dos 46 Operadores |
| — | Convenção de ID de regra (`PREFIXO-NNN`: `SRE-002`, `EH-003`, `GOVDEBT-001`, `SWEEP-001`, `META-001/002`) preservada em `RuleDefinition.id` |
| — | **"ledger"**, **"gate"**, **"sweep"**, **"patrol"**, **"deferred"**, **"supressoes"** preservados como nomes informais dos mecanismos equivalentes |

## Idioma

Documentação, comentários e docstrings em português — mesma língua da
especificação e do Batman atual. Identificadores de código (classes, funções,
variáveis) em inglês, espelhando o pseudocódigo da especificação.

## Comandos

```bash
python3.11 -m venv .venv
.venv\Scripts\activate            # Windows

pip install -e ".[dev]"

pytest                             # todos os testes de aceitação (AT-X.Y)
mypy src/
ruff check src/ tests/
```

## Portão automático (CI)

Dois mecanismos rodam `pytest` + `mypy` + `ruff check` + `ruff format --check`
automaticamente, não só manualmente (mesmo padrão já usado no `radar-preditivo`):

- **`.github/workflows/ci.yml`** — roda em todo push/PR para `main` assim que o
  repositório tiver um remoto no GitHub (não precisa de remoto para o arquivo
  existir, só para o workflow disparar).
- **Hook `pre-push` local** — bloqueia o `git push` se qualquer verificador falhar.
  Não é versionado pelo git (`.git/hooks/` fica de fora do repositório) — instalar
  em cada clone novo:
  ```bash
  cp scripts/git-hooks/pre-push .git/hooks/pre-push
  chmod +x .git/hooks/pre-push
  ```
