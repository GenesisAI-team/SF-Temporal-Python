# Runbook — pipeline H2+H3: de issue aprobada a PR (GEN-47/GEN-52)

## Qué produce

Una issue aprobada (`GEN-N`) con `SF_FACTORY_PIPELINE_ENABLED=true` y una
`ApprovedTaskSpec` en fichero dispara el flujo durable
`issue-<GEN-N>` (Temporal) que:

1. `PLANNING`: resuelve la spec aprobada desde `SF_FACTORY_TASK_SPEC_PATH`
   y deriva `run_key` (`GEN-N-v1`) y rama determinista
   `feat/gen-<n>-<slug>` (slug ASCII del título).
2. `PREPARING`: comprueba el presupuesto (`SF_FACTORY_BUDGET_RUNS_PER_ISSUE`,
   libro en `SF_FACTORY_RUN_LEDGER_PATH`) y garantiza el workspace
   (`SF_FACTORY_WORKSPACE_ROOT/<run_key>`, resuelto a ruta absoluta para Git
   y para el bind-mount de Docker) con la rama desde
   `SF_FACTORY_BASE_BRANCH`.
3. `IMPLEMENTING`: una sesión `codex exec` dentro de un sandbox Docker
   efímero (`factory-sandbox-<run_key>`), sin red, sin credenciales,
   rootfs read-only, CPU/RAM acotados, comandos peligrosos bloqueados por
   la deny-list de `domain/safety.py`.
4. `VERIFYING` (H3): suite de quality gates independientes en un sandbox
   nuevo — `tests` (`uv run pytest -q`), `lint` (`uv run ruff check .`) y
   `typecheck` (`uv run mypy src`) — cada gate con su evidencia (colas de
   salida). Un gate fallido no impide los demás; los pasos de un gate se
   detienen en su primer fallo.
5. `REVIEWING` (H3): sesión de revisión independiente (SU PROPIA sandbox,
   separada del implementador) que contrasta la diff contra la spec
   aprobada y responde `APPROVED`, `DEFECT: ...` o `SPEC_DRIFT: ...`.
   `SPEC_DRIFT` bloquea sin reparar; `REVIEW_FAILED` (sin veredicto)
   bloquea; defectos → repair loop.
6. `REPAIRING` (H3, acotado): si fallan los gates o la revisión reporta
   defectos, el agente se re-ejecuta con el feedback (`defects` en el
   prompt) y el ciclo gates → revisión se repite. Presupuesto:
   `SF_FACTORY_REPAIR_ATTEMPTS` (2 por defecto; 0 = sin reparación)
   sobre el mismo run key; límites de tiempo por fase (agente 30 min,
   gates 15 min, revisión 10 min); un sandbox efímero por sesión (coste).
   Agotado el presupuesto → `BLOCKED` con `REPAIR_BUDGET_EXHAUSTED` y el
   último fallo adjunto. Cada intento deja la línea de auditoría
   `delivery#run_key#REPAIRING#<n>` (los reintentos no duplican).
7. Publicación: `git add -A` + commit convencional + `git push` (nunca
   force) + apertura/reutilización de PR con `gh` (busca PR abierta por
   head-branch para no duplicar). El cuerpo del PR lleva la evidencia
   verificada (`## Verified evidence`).
8. `PR_READY`: memo + línea de auditoría con la URL del PR.

Cada fase deja exactamente una línea en `SF_AUDIT_LOG_PATH` (auditoría
append-only; los reintentos no duplican; las reparaciones, una por
intento). Los fallos funcionales terminan en `BLOCKED` con código estable
(ver ADR-0008/0009); los fallos técnicos se reintentan por política de
fase y, agotados, dejan el workflow en FAILED para reset del operador
(la re-ejecución no duplica trabajo).

## Preconditions (GPIO del operador)

- `docker` disponible en el host del worker (versión compatible con el
  compose del repo). Sin docker: `SandboxUnavailable` → reintentos → FAILED.
- Git disponible y credenciales de push configuradas por el operador para
  el repositorio objetivo (H2 las gestiona FUERA del sandbox). El slug
  `owner/name` se resuelve a la URL de transporte configurada en
  `SF_FACTORY_GIT_TRANSPORT_URL_TEMPLATE` (por defecto
  `https://github.com/{repository}.git`); una URL o ruta local se usa tal
  cual. La
  identidad de los commits es explicita por entorno
  (`SF_FACTORY_GIT_USER_NAME` / `SF_FACTORY_GIT_USER_EMAIL`; por defecto
  `SF-Temporal-Python Factory <factory@sf-temporal.local>`) — no depende
  de la configuración global de git del host (requerido en CI).
- `gh` CLI autenticado si se quiere abrir PRs reales en GitHub.
- Imagen de sandbox que contenga el CLI de Codex para ejecución REAL
  (`SF_FACTORY_SANDBOX_IMAGE=ghcr.io/...`); la imagen por defecto
  (`python:3.12-slim`) no incluye el CLI: los runs fallarán honestamente
  con `AGENT_FAILED` si se intenta `codex exec` sin él. Esto NO simula
  éxito — ver "Real vs simulado" abajo.

## Ejecución local (sin secretos)

```bash
uv sync --frozen
docker compose -f infrastructure/docker/compose.yaml up -d --wait
# 1) fichero de spec aprobada (manual del operador; aquí un ejemplo de smoke)
cat > /tmp/spec.json <<'JSON'
{
  "issue_id": "GEN-47",
  "spec_version": 1,
  "repository": "GenesisAI-team/SF-Temporal-Python",
  "base_branch": "main",
  "objective": "H2: PR desde issue aprobada",
  "acceptance_criteria": ["rama y PR únicos", "auditoría por fase"]
}
JSON
# 2) stack + smoke end-to-end (usa git local y dbls explícitos; sin tokens)
uv run pytest tests/integration -m integration -v
# 3) worker con pipeline habilitada
SF_FACTORY_PIPELINE_ENABLED=true \
SF_FACTORY_TASK_SPEC_PATH=/tmp/spec.json \
SF_LINEAR_TARGET_REPOSITORY=GenesisAI-team/SF-Temporal-Python \
SF_LINEAR_WEBHOOK_SECRET=dev-secret \
uv run python -m super_factory.temporal.workers.run
```

La UI de Temporal (http://localhost:8233) muestra el run `issue-<GEN-N>`
con memo `workflow_state` avanzando de PLANNING a PR_READY.

## Real vs simulado en esta PR (GEN-47)

| Pieza | Estado en H2 |
| --- | --- |
| Webhook Linear (firma/replay/dedupe) | REAL (H1) |
| IssueWorkflow + selección + auditoría | REAL |
| Puertos/actividades del pipeline + workflow H2 | REAL (código fusionado y probado) |
| Spec aprobada | REAL vía `SF_FACTORY_TASK_SPEC_PATH` (fichero del operador) |
| Sandbox Docker | Adaptador REAL (docker run/exec/rm vía `CommandRunner`); probado con runner simulado |
| Agente Codex (sesión real) | ADAPTADOR REAL PENDIENTE DE OPERACIÓN: exige imagen con CLI `codex`; los tests y smokes usan dobles explícitos |
| Verificación (gates H3) | Adaptador REAL (suite tests/lint/typecheck en sandbox); smoke usa doble explícito |
| Revisión independiente (H3) | ADAPTADOR REAL PENDIENTE DE OPERACIÓN: exige imagen con CLI del revisor; sin ella `REVIEW_FAILED` honesto; los tests y smokes usan dobles explícitos |
| Git commit/push | REAL (`git` CLI); smoke contra bare remote local |
| GitHub PR | Adaptador REAL (`gh` CLI) probado con runner simulado; el smoke usa doble |

## Limpieza y límites

- `cleanup` del sandbox: `docker rm -f factory-sandbox-<run_key>` best-effort
  en todas las rutas del agente y del verificador; los contenedores nunca
  superan la vida de la sesión.
- Presupuesto: `SF_FACTORY_BUDGET_RUNS_PER_ISSUE` (2 por defecto) cuenta
  run keys distintos por issue (ledger persistente); reintentos técnicos
  del mismo run key no consumen presupuesto. Las reparaciones H3
  (`SF_FACTORY_REPAIR_ATTEMPTS`, 2 por defecto) reutilizan el run
  reservado: no tocan el presupuesto de runs.
- Logs sin secretos: ni firma/secreto/payload de Linear en líneas de
  auditoría; el sandbox no recibe env heredadas.
