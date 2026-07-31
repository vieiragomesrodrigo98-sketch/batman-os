# Contrato de paridade — Observe/Watcher (legado → Batman OS)

Princípio da migração (decisão do Rodrigo, 2026-07-22): **nenhuma
funcionalidade se perde; só melhora.** Este documento é o critério de
aceite do subsistema `batman_os/observe/`. Cada linha do legado
(`radar-preditivo/Batman/observe/`) tem um destino explícito no Batman OS.
Nada pode ficar "para trás" sem estar aqui como decisão consciente.

Legenda: **=** porta com comportamento idêntico · **+** porta e melhora ·
**✗→✓** funcionalidade que o legado tem mas está QUEBRADA/MORTA e o Batman
OS entrega funcionando.

## Coleta (collector.py → observe/collectors.py)

| Capacidade legada | Destino no Batman OS | |
|---|---|---|
| CPU/RAM/disk via psutil | `InfraCollector` (psutil, extra opcional) | = |
| Endpoint: GET status + latência | `EndpointCollector` (probe HTTP) | + detecta **down real** (timeout/conn-refused), não só 5xx |
| Portas em escuta (LISTEN + bind real) | `PortCollector` | = |
| Tail de log nginx | `LogCollector` | = |

## Regras de alerta (dispatcher.py + watch_rules/* → observe/watch_rules.py)

**Correção estrutural (BATBL-007):** o legado tem DUAS pilhas divergentes —
`dispatcher.py` (viva) e `watch_rules/*.py` (morta, thresholds diferentes).
O Batman OS terá **UMA fonte canônica** de regras; a divergência morre aqui.

| Regra | Threshold canônico (o melhor das duas pilhas) | Severidade | |
|---|---|---|---|
| CPU alto | ≥80 WARNING / ≥90 CRITICAL | | = |
| RAM alto | ≥80 WARNING / ≥90 CRITICAL | | = |
| Disco alto | ≥80 WARNING / ≥90 CRITICAL | | = |
| Latência | **p95 real** ≥500ms WARN / ≥1000ms CRIT | | + legado mandava latência de 1 request rotulada como "p95"; agora janela real |
| Taxa de 5xx | ≥2% WARN / ≥5% CRIT (sustentado) | | = |
| **Endpoint down** | ok=False → CRITICAL | | ✗→✓ (só existia na pilha morta; daemon vivo nunca emitia) |
| Porta nova | loopback→WARNING; externa→CRITICAL | | + `@everyone` só p/ serviço perigoso (Redis/DB/SSH); enriquece com nome do serviço |
| SSH brute-force | ≥10 WARNING / ≥20 CRITICAL | | + `auth_bypass` de fato calculado (legado hardcodava False) |
| Porta inesperada aberta | allowlist → HIGH | | = |
| **Processo suspeito** | nmap/xmrig/sqlmap/metasploit → CRITICAL | | ✗→✓ (só na pilha morta) |
| Brute-force 404 | IP com ≥30 404 → WARNING | | = |
| Não-autorizado | 401/403 ≥15% em ≥20 req → WARNING | | = |
| **Serviço caído** (process_down) | processo esperado ausente → CRITICAL | | ✗→✓ (regra existia no dispatcher, nunca emitida) |
| **Config nginx inválida** (nginx_change) | | | ✗→✓ (idem) |
| **Headers de hardening ausentes** | | | ✗→✓ (idem) |
| **Endpoint exposto** (endpoint_exposed) | | | ✗→✓ (idem) |

## Entrega (discord_alert.py → governance/alert_sinks.py) — JÁ FEITO

| Capacidade legada | Batman OS | |
|---|---|---|
| Webhook Discord, embeds por severidade, retry 429, backoff | `DiscordAlertSink` | = |
| Roteamento por canal (rule_type/severidade) | roteamento por **tenant** (ADR-0005) | + |
| Debounce por cooldown fixo 300s | **dedupe por estado** (só reenvia se mudou) | + mata o ruído ARCH-007 (idêntico 3 dias) |
| `@everyone` p/ qualquer porta externa | `@everyone` só p/ fontes na allowlist | + |
| hostname da VPS no footer | só o tenant no footer | + sem vazar topologia |

## Loop/agendamento (daemon.py + patrol.py → observe/watcher.py)

| Capacidade legada | Batman OS | |
|---|---|---|
| Loop `while True` + sleep 60s (systemd) | `ObserveWatcher.run_forever(intervalo)` + `run_once()` testável | = |
| Debounce (300s / 12h manutenção) | herdado do sink (dedupe por estado) + cooldown por regra | + |
| Patrulha diária: heartbeat "tudo limpo OU atenção" ao #log | `heartbeat()` do watcher: batimento periódico mesmo limpo | = |
| **Self-heartbeat do daemon** | batimento do próprio watcher a cada N ciclos | ✗→✓ (legado ficou 22 dias mudo sem ninguém notar) |
| Persistência de alertas (SQLite `batman_observe.db`) | `GovernanceEngine` já persiste + Event Bus | = |

## Restrições arquiteturais (não violar)

- `observe/` importa `governance` + `foundation` + stdlib/psutil. **NÃO importa `batman_os.kernel`** (mesma disciplina do sink; coerente com ADR-0012 para o caminho de governança).
- Multi-tenant: coletas e alertas carregam `tenant_id`; o sink roteia por tenant (ADR-0005).
- Toda entrega é best-effort: falha de coleta/entrega nunca derruba o loop.
- `psutil` é dependência opcional (extra `observe`), como `llama-cpp-python` é do `local-llm`.
- Capacidade nova (watcher + entrega externa) formalizada como **Anexo** ao Cap.27/30 (StatusAnexo), por não estar na spec original.

## Critério de aceite

O subsistema está pronto quando: (1) toda linha marcada **=**, **+** ou
**✗→✓** acima tem implementação + teste; (2) as 5 regras `✗→✓` que o legado
nunca emitia passam a emitir; (3) o watcher roda `run_once()` sobre um
snapshot fake e produz exatamente os `GovernanceAlert` esperados; (4)
suíte verde, ruff limpo, mypy sem erro novo.
