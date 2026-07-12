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
I–X). Ver `docs/spec/SUMMARY.md` para o índice completo. Volumes VIII
(Infrastructure) e X (Appendices) são volumes de topologia física e consolidação
— não introduzem componentes de código novos a implementar (ver nota sobre o
Cap.32 abaixo).

**Migração do catálogo Batman: 271/271 regras** (concluída em 2026-07-10),
validada por comparação de fingerprint byte-a-byte contra o motor legado
(`scripts/compare_migracao.py`) rodando contra o `radar-preditivo` real.

**Roadmap de plataforma: Fases 1–11 concluídas** (2026-07-12) — de "Scanner
Determinístico" a "Plataforma Operacional de Engenharia": Kernel/Runtime com
persistência real e paralelismo (`EventBus`/`OperationalMemory` em SQLite,
`runtime/dispatcher.py`), isolamento multi-tenant estrutural em leitura e
mutação, Playbooks multi-step com decision points reais na autoria, Mission
Graph (`learning/mission_reconciliation.py`), e uma API HTTP completa e
autenticada (ver seção "API HTTP" abaixo). **1058 testes, `mypy`/`ruff`
limpos.** Status detalhado, o que existe hoje e o backlog de trabalho futuro
(com contexto e justificativa por item) em
[`docs/PLATFORM_ROADMAP_BACKLOG.md`](docs/PLATFORM_ROADMAP_BACKLOG.md).

## Estrutura

```
docs/spec/          # especificação completa (fonte da verdade — só leitura para o código)
src/batman_os/
  foundation/        # Vol. I — tipos oficiais do glossário (Mission, Capability, etc.)
  kernel/            # Vol. II — Mission Runtime, Planning/Decision/Workflow Engine, Event Bus, Scheduler
  runtime/           # Vol. III — Capability Engine, Execution Engine, Operational Memory, Concorrência
  capabilities/      # Vol. IV — Operator, certificação de Capability, Skills, Tools, Cooperação
    rules/           # Capabilities migradas do Batman atual (não é um Volume da spec)
  workflow/          # Vol. V — Missões formais, Playbooks, Recuperação/Fallback
  learning/          # Vol. VI — Knowledge Graph, Rule/Workflow Evolution, Operational Learning
  governance/        # Vol. VII — Governance Engine, Human Review, LLM Escalation, Observability Engine
  orchestration/     # canalização Kernel+Runtime+Capabilities -> fluxo executável (não é um Volume)
  cli/               # entry point `batman` (Vol. IX Cap.34, Fase 0 — Walking Skeleton)
tests/               # 1 arquivo de teste por capítulo, nomeado pelos próprios AT-X.Y da spec
scripts/
  compare_migracao.py  # compara fingerprints do batman-os com o motor legado, no mesmo alvo real
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

batman scan --root <repo>          # roda o primeiro lote de Capabilities migradas contra um repo real
batman scan --root <repo> --fail-on high   # saida 1 se houver achado high/critical
```

## API HTTP

Fases 6-8 do roadmap de plataforma ([`docs/PLATFORM_ROADMAP_BACKLOG.md`](docs/PLATFORM_ROADMAP_BACKLOG.md))
adicionaram uma API HTTP (FastAPI) sobre o mesmo Kernel — `pip install -e ".[api]"`
para instalar `fastapi`/`uvicorn`/`httpx`.

```bash
uvicorn batman_os.api.app:criar_app --factory
```

Toda requisição a `/missions/*` e `/jobs/*` exige autenticação real via
`Authorization: Bearer <chave>` — não existe mais seleção de tenant sem prova
(Fase 8). Configure `BATMAN_API_KEYS` no `.env` (objeto JSON `tenant->chave`, ver
`.env.example`) antes de subir o servidor; gere uma chave nova com:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Sem header válido, todo endpoint responde `401`. O tenant aplicado à Missão é
derivado 100% da chave usada — nunca de um campo do corpo da requisição.

```bash
curl -X POST http://localhost:8000/missions/security-audit \
  -H "Authorization: Bearer <sua-chave>" \
  -H "Content-Type: application/json" \
  -d '{"root": "/caminho/do/repo"}'
# -> 202 {"mission_id": "..."}

curl http://localhost:8000/jobs/<mission_id> \
  -H "Authorization: Bearer <sua-chave>"
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
