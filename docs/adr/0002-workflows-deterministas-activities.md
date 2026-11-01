# ADR-0002: Workflows deterministas, efectos solo en Activities

- **Estado:** Aceptado (GEN-17)
- **Contexto:** Temporal replaya workflows para recuperación y versionado. Cualquier no-determinismo (red, fechas reales, aleatoriedad, Docker, modelos) rompe el replay.
- **Decisión:**
  - Los módulos de `temporal/workflows/` **solo** contienen orquestación: `workflow.*`, imports pasados con `workflow.unsafe.imports_passed_through()` para contratos/activities.
  - Todo efecto externo (HTTP, git, Docker, modelos, filesystem) se ejecuta en `temporal/activities/`.
  - Activities largas usan `heartbeat_timeout` + `activity.heartbeat()`; las operaciones bloqueantes (H2: Codex, Docker) deben ser síncronas y registrarse con `activity_executor` en el `Worker` (las activities puras async no lo necesitan — verificado con `temporalio` 1.35.0).
- **Consecuencias:** Más archivos, pero el replay funciona siempre; los tests de workflow usan `WorkflowEnvironment.start_time_skipping` y `Replayer`.
- **Ejemplo real en este repo:** `SmokeWorkflow` importa `EchoInput`/`echo_activity` con `imports_passed_through` y solo usa `workflow.execute_activity` + `workflow.info()`.
