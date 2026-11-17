# Evidencia — GEN-47 (H2: Codex + sandbox + GitHub → PR desde issue aprobada)

> Ejecutada por el worker de la Genesis Factory (opencode) el 2026-11-10.
> Base: `main` @ `be5cc1f` (H1 GEN-38 merged). Rama:
> `feat/GEN-47-h2-codex-sandbox`. Entorno: Windows (PowerShell), Python 3.12
> vía uv, Temporal local por docker compose (Imagen de issue: GEN-47).

## 0. Preparación

```text
$ git fetch origin --prune
   13d2a46..be5cc1f  main       -> origin/main          # H1 merged (PR #2)
$ git checkout -b feat/GEN-47-h2-codex-sandbox origin/main
$ uv sync --frozen                                     # exit 0
$ uv run pytest tests/unit -q → 189 passed             # baseline
$ uv run pytest tests/temporal -q → 13 passed          # baseline
$ uv run ruff check . → All checks passed!
$ uv run mypy src → Success: no issues found in 45 source files
```

## 1. TDD RED→GREEN (fases de la issue)

### Fase 1 — contratos + reglas de dominio

RED (implementación ausente, se paró deliberadamente antes del run):

```text
$ uv run pytest tests/unit/test_domain_pipeline.py tests/unit/test_domain_safety.py \
     tests/unit/test_pipeline_contracts.py -q
ERROR tests/unit/test_domain_pipeline.py
ERROR tests/unit/test_domain_safety.py
ERROR tests/unit/test_pipeline_contracts.py
E   ModuleNotFoundError: No module named 'super_factory.contracts.pipeline'
3 errors in 0.26s                                       # exit 2
```

GREEN:

```text
$ uv run pytest tests/unit/test_domain_pipeline.py ... -q
41 passed in 0.22s                                      # exit 0
```

Iteración documentada: 38 + 3 en fallo → 3 invariantes corregidos
(slug de acentos sin separador, alternancia `| python` en RCE, cuerpo del
fork bomb) — el DENY-LIST de `domain/safety.py` pasó sus 12 casos.

### Fase 2 — puertos + adaptadores (process/sandbox/agents/scm/planning/ledger)

RED por bloques:

```text
E   ModuleNotFoundError: No module named 'super_factory.process.subprocess'
E   ModuleNotFoundError: No module named 'super_factory.sandbox.docker'
E   ModuleNotFoundError: No module named 'super_factory.scm.git_cli'
E   ModuleNotFoundError: No module named 'super_factory.scm.github_cli'
E   ModuleNotFoundError: No module named 'super_factory.agents.codex_cli'
E   ModuleNotFoundError: No module named 'super_factory.persistence.run_ledger'
6 errors during collection
```

GREEN: `55 passed`. Defectos capturados y corregidos en el bucle:
stub sin `self.script` (AttributeError), cleanup del agente (paso de
`instance.id` en vez de instancia), `SandboxCommandOutcome.exit_code`
no-Optional int, stdin del subprocess sin PIPE explícito.

### Fase 3 — actividades + IssueWorkflow extendido

RED:

```text
E   ModuleNotFoundError: No module named 'super_factory.temporal.activities.pipeline'
ERROR ... 2 errors during collection
```

GREEN con 330 tests (incl. 11 escenarios Temporal). Hallazgos reales:

```text
AssertionError: REVIEWING      # faltaba la línea de auditoría de REVIEWING
E  pydantic ValidationError     # SandboxCommandOutcome.exit_code debe ser int | None
NameError 'VerificationOutcome' # errores de import en tests (no en src)
```

Extraído del fallo "hang" del escenario publish (Temporal/pytest): el
repro asyncio y el scratch mínimos demostraron que el reintentar-wall ya
fallaba en ~7s; el workaround fue aislar el escenario en un bucle propio
(`asyncio.run`) — comportamiento idéntico en la llamada al bucle real de
pytest-asyncio... El test final:
`1 failed ... assert 'gh down' in text` — se corrigió el assert para
inspeccionar la CAUSA (_workflow failure envelope no lleva el detalle).

### Fase 4 — smoke end-to-end (stack real)

```text
$ docker compose -f infrastructure/docker/compose.yaml up -d --wait
 Container docker-temporal-1 Healthy    # exit 0
$ uv run pytest tests/integration -m integration -v
tests/integration/test_issue_workflow_roundtrip.py::... PASSED
tests/integration/test_pipeline_smoke.py::test_h2_pipeline_produces_branch_and_pr_without_tokens PASSED
tests/integration/test_worker_roundtrip.py::... PASSED
3 passed in 5.47s
```

Hallazgos reales en el smoke: (a) los run-scores previos dejaron el run
`issue-GEN-47` con ALLOW_DUPLICATE default del cliente y colapsaron el
`execute_workflow` de la reentrada; (b) la spec aprobada debe
instanciarse por run key — corregido instanciando en el harness (un
deleted-zombie del arranque anterior se resolvió con `compose down -v`).
El estado FINAL del smoke demuestra: rama empujada al bare local,
commit `feat(GEN-47): ...` en `git log --branches`, 1 PR simulado,
audit SELECTED + fases exactamente 1 vez por fase, 1 registro en el
ledger (`<issue>-v1`) y recovery del duplicado vía el adaptador real
`IssueWorkflowStarter` (REJECT_DUPLICATE, `started=False`).

## 2. Gates finales (locales)

```text
$ uv run ruff check .            → All checks passed!
$ uv run mypy src                → Success: no issues found in 68 source files
$ uv run pytest tests/unit tests/temporal -q → 335 passed in 17.01s
$ uv run coverage run -m pytest tests/unit tests/temporal -q
335 passed in 18.76s             → coverage policy OK (per-file 100/80)
$ uv run pytest tests/integration -m integration -v → 3 passed in 5.47s
```

## 3. Commits de la rama

| Hash | Mensaje |
| --- | --- |
| `ba65473` | feat(GEN-47): H2 contracts, domain rules and replaceable ports/adapters |
| `b4d586f` | feat(GEN-47): H2 PR-production pipeline activities + IssueWorkflow extension |
| `3c7bd9b` | feat(GEN-47): H2 end-to-end smoke on the real Temporal stack (no tokens) |
| `985451d` | docs(GEN-47): ADR-0008 (PR pipeline H2), runbook pipeline, env example, architecture + evidence docs |
| `a465693` | fix(GEN-47): explicit git identity for factory commits (CI hosts lack global config) |

## 5. CI de la PR (checks obligatorios)

```text
$ gh pr create --base main  → https://github.com/GenesisAI-team/SF-Temporal-Python/pull/3
$ gh pr checks 3
quality       pass   25s   # 336 tests, ruff, mypy strict, coverage 100/80
integration   pass   35s   # compose up + 3 integration tests (roundtrip + smoke)
```

Iteración de CI documentada: el primer run de integración falló en CI por
`git commit failed: Author identity unknown` (los runners de CI no tienen
config global de git; local sí). Corregido con identidad git explícita por
entorno (`SF_FACTORY_GIT_USER_NAME/EMAIL` aplicada con `-c` en el commit;
tests + runbook). Segundo run: quality PASS e integration PASS.

## 4. Qué es REAL vs SIMULADO (resumen honesto)

- REAL: H1 completo (webhook/selection/audit/dedupe); H2 planning con fichero aprobado; workflow
  extensor; actividades; sandbox Docker adapter (comandos docker probados con runner simulado: se
  verifican módulos y política, no el daemon); agente Codex adapter (mapeo de outcomes y cleanup
  probado con sandbox simulado; la sesión `codex exec` REAL necesita imagen con el CLI y queda en
  operación); verificación (adapter real, smoke con doble); git real commit/push (smoke con bare
  remoto local); gh adapter (probado con runner simulado).
- SIMULADO (explícito y auditado): sandbox runtime, Codex agent, verification runner y GitHub PR en
  unit/Temporal/tests de integración (dobles explicados en docstrings); ninguno se proclama real.
- Tokens: ningún token real en el repo o en CI; el smoke no necesita credenciales (git local + paths).
