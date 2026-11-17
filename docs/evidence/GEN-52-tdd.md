# Evidencia TDD — GEN-52 (H3: quality gates, revisión independiente, repair loop acotado)

Rama: `feat/GEN-52-h3-quality-gates` (desde `main` @ 02d0128, merge de H2/PR #3).
Metodología: RED → GREEN → REFACTOR por ciclo, coberturas per-file 100/80/0.

## Ciclo 1 — dominio, contratos, gates y revisor

**RED.** Cuatro suites nuevas fallan porque los módulos no existen
(motivo correcto: `ModuleNotFoundError: No module named
'super_factory.contracts.quality'`):

```text
tests/unit/test_domain_quality.py
tests/unit/test_quality_contracts.py
tests/unit/test_quality_gates_runner.py
tests/unit/test_review_sandbox.py
4 errors in 0.46s (collection interrupted)
```

**GREEN.** Implementación mínima:

- `src/super_factory/domain/quality.py` — `GateDefinition`,
  `default_gate_suite()` (tests/lint/typecheck, argv puro), parse del
  veredicto (`parse_review_reply`, `reviewer_approved`), reglas de drift
  (`has_spec_drift`, `review_failure_code_for`), feedback de reparación
  (`defect_feedback`, `gate_failure_feedback`), resúmenes de evidencia
  (`summarize_gate`), ids de auditoría por intento
  (`repair_audit_delivery_id` → `delivery#run_key#REPAIRING#<n>`) y
  `build_reviewer_prompt`.
- `src/super_factory/contracts/quality.py` — `GateOutcome`,
  `ReviewFinding`, `ReviewCommand`, `ReviewOutcome` (validación cruzada del
  eje ok/fallo: `SPEC_DRIFT` ⟺ `spec_drift`, `REVIEW_REJECTED` solo
  hallazgos DEFECT, `REVIEW_FAILED` sin veredicto).
- Extensiones H2 compatibles: `VerificationOutcome.gates`,
  `AgentRunCommand.defects`, `PublishCommand.gate_summaries`,
  `IssueWorkflowInput.max_repair_attempts`, `pr_body_for` con sección
  `## Verified evidence`, `build_agent_prompt` con bloque
  `Repair feedback` solo cuando hay defectos.
- `src/super_factory/verification/quality_gates.py` —
  `SandboxQualityGatesRunner` (reemplaza `verification/sandbox.py`, que se
  elimina): gates independientes, pasos de un gate paran en su primer
  fallo, `GATE_FAILED` por gate y `VERIFICATION_FAILED` agregado.
- `src/super_factory/review/{ports,sandbox}.py` — port
  `IndependentReviewer` y adaptador `SandboxReviewer` (sesión separada,
  parse determinista fail-closed, cleanup en todas las rutas).

Ajustes de refactor durante el verde: regex de test ("findings" vs
"finding"), igualdad de `ReviewFinding` en asserts, importación de
`REASON_*` faltantes.

## Ciclo 2 — workflow (revisión + repair loop acotado)

**RED.** `tests/temporal/test_issue_review_repair.py` (10 escenarios)
falla porque el workflow no tenía fase de revisión ni reparación: p. ej.
`test_spec_drift_blocks_without_repair` terminaba en `PR_READY` en vez de
`BLOCKED/SPEC_DRIFT`.

**GREEN.** `IssueWorkflow` extiende la fase de PR:

- `VERIFYING` ejecuta la suite de gates; `REVIEWING` es ahora la revisión
  independiente (auditada antes de publicar).
- `REPAIRING`: re-ejecución del agente con feedback de gates/defectos,
  presupuesto `max_repair_attempts` (0 = sin reparación), timeout por
  fase como límite de tiempo, y `BLOCKED` con `REPAIR_BUDGET_EXHAUSTED`
  (agotado), `AGENT_FAILED` (sesión de reparación rota), `SPEC_DRIFT`
  (drift, sin reparación) o `REVIEW_FAILED` (revisor sin veredicto).
- Auditoría por intento `...#REPAIRING#<n>` (idempotente por intento);
  memo avanza a `REPAIRING` con el número de intento.

Defecto cazado en GREEN: pasar `ReviewFinding` (dataclass) a
`defect_feedback` (espera pares primitivos) provocaba un fallo de tarea de
workflow con reintento infinito (test colgado). Corregido en el punto de
llamada del workflow convirtiendo a pares `(kind, detail)`.

## Escenarios de aceptación (tests temporales)

1. **PR pasa/falla según evidencias verificadas** —
   `test_evidenced_pr_publishes_after_gates_and_review`: gates → revisión
   → publicación; el cuerpo del PR lleva `## Verified evidence` con los
   resúmenes de gates; el comando de revisión recibe la spec aprobada y
   las evidencias.
2. **Defectos → reparación acotada sin bucles infinitos** —
   `test_gate_failure_triggers_one_bounded_repair_then_publishes`,
   `test_review_defects_trigger_bounded_repair_then_publishes`,
   `test_persistent_gate_failures_exhaust_the_repair_budget` (2 intentos,
   luego `REPAIR_BUDGET_EXHAUSTED`),
   `test_zero_repair_budget_blocks_at_the_first_gate_failure`,
   `test_repair_budget_also_bounds_review_rejections`,
   `test_failing_repair_session_blocks`.
3. **Spec drift bloquea** — `test_spec_drift_blocks_without_repair`
   (`BLOCKED/SPEC_DRIFT`, cero reparaciones, cero publicación) y
   `test_verdictless_review_blocks_without_repair` (`REVIEW_FAILED`).
4. **Reintentos/fallo** — `test_transient_agent_outage_is_absorbed_by_retries`
   (H2, sigue verde), auditoría idempotente por intento, y
   `test_repair_history_replays_deterministically` (replay de la historia
   con reparación).

## Actualización de tests H2 (semántica H3)

- `test_pipeline_verification_failure_blocks` →
  `test_persistent_gate_failures_block_after_the_repair_budget` (el fallo
  de verificación ya no bloquea directamente; alimenta la reparación
  acotada).
- `tests/unit/test_verification_sandbox.py` eliminado (sustituido por
  `tests/unit/test_quality_gates_runner.py`).
- Humo de integración: revisor simulado explícito (`_ApprovingReviewer`).

## Gates finales (locales, misma línea que CI)

```text
uv run ruff check .                                  → All checks passed!
uv run mypy src                                      → Success: no issues found in 73 source files
uv run pytest tests/unit tests/temporal -q           → 407 passed
uv run coverage run -m pytest tests/unit tests/temporal -q
uv run coverage combine && uv run coverage json -o coverage.json
uv run python -m scripts.check_coverage              → coverage policy OK (per-file 100/80)
```

Cobertura de los archivos nuevos: `domain/quality.py`,
`contracts/quality.py` (CORE: 100 % líneas y ramas);
`verification/quality_gates.py`, `review/ports.py`, `review/sandbox.py`
(IMPORTANT: ≥ 80 %); registrados en `scripts/check_coverage.py` en esta
misma PR.

## Ciclos 3–5 — arreglo de los hallazgos de revisión de PR temporal#4

Tres hallazgos de `chatgpt-codex-connector` (hilos 4601404819, 4601404814,
4601404847), cada uno con su ciclo RED → GREEN sobre la rama de la PR.

**Ciclo 3 — P1: historiales pre-cambio no podían reanudarse (issue.py).**
RED: `tests/temporal/test_issue_workflow_compat.py` genera historiales con
una referencia byte-fiel de la implementación H2
(`tests/temporal/h2_reference.py`, incluidas las shapes de entrada de
GEN-47) y el replay con la implementación H3 falla por el motivo correcto:

```text
temporalio.workflow._exceptions.NondeterminismError: [TMPRL1100]
Activity type of scheduled event 'publish_pr_activity' does not match
activity type of activity command 'review_run_activity'
```

(los 3 escenarios: PR_READY, BLOCKED por gates, BLOCKED por changeset
vacío). GREEN: patch marker `review-before-publish` (API
`workflow.patched`) justo delante del primer comando divergente (la forma
del input del agente); las historias sin marker toman la rama legacy
(`_legacy_verify_publish`, `LegacyAgentRunCommand`,
`LegacyPublishCommand`) que reproduce la secuencia H2 byte a byte,
incluidas las serializaciones sin `defects`/`gate_summaries`. Los tres
escenarios pasan, y el replay de historias H3 sigue en verde
(`test_repair_history_replays_deterministically`).

**Ciclo 4 — P1: los defectos no llegaban al prompt del agente real
(codex_cli.py).** RED:
`test_agent_prompt_carries_repair_defects_via_stdin` —payload real de
stdin, no solo el comando del fake agent— falla porque
`CodexCliAgent.run()` llamaba a `build_agent_prompt()` sin
`command.defects`. GREEN: `defects=command.defects` en la llamada;
`test_agent_prompt_has_no_repair_block_on_first_session` fija que la
primera sesión no lleva bloque de reparación.

**Ciclo 5 — P2: el revisor podía mutar el artefacto (sandbox.py).** RED:
tres tests (`test_reviewer_starts_read_only_workspace_sandbox`,
`test_ensure_sandbox_can_mount_workspace_read_only`,
`test_sandbox_spec_defaults_secure`) fallan por
`'SandboxSpec' object has no attribute 'workspace_read_only'`. GREEN:
`SandboxSpec.workspace_read_only` (default False), el runtime Docker monta
`/workspace:ro` cuando está activo, y `SandboxReviewer` lo activa: la
revisión no puede alterar el artefacto que se publica tras su veredicto.

## Gates tras los arreglos (locales, misma línea que CI)

```text
uv run ruff check .                                  → All checks passed!
uv run mypy src                                      → Success: no issues found in 73 source files
uv run pytest tests/unit tests/temporal -q           → 414 passed
uv run coverage run -m pytest tests/unit tests/temporal -q
uv run coverage combine && uv run coverage json -o coverage.json
uv run python -m scripts.check_coverage              → coverage policy OK (per-file 100/80)
```

Workflow (CORE) sigue en 100 % líneas y ramas, incluida la rama legacy de
replay (cobrada por los tres escenarios de compat).
