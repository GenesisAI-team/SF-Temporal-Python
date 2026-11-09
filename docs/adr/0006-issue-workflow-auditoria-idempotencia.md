# ADR-0006: IssueWorkflow durable y auditoría de selección (H1)

- **Estado:** Aceptado (GEN-38)
- **Contexto:** H1 transforma eventos de issues aprobadas en ejecuciones durables de Temporal: la selección debe correlacionar issue/repositorio/workflow y persistir razones de bloqueo, sin programar agentes de código todavía (H2). En H1 no hay base de datos desplegada.
- **Decisión:**
  - `IssueWorkflow` (`temporal/workflows/issue.py`) ejecuta **un solo run durable por issue** con id determinista `issue-<GEN-N>` y `WorkflowIDReusePolicy.REJECT_DUPLICATE`: un evento válido crea **o recupera** una única ejecución; reintentos y duplicados no duplican trabajo.
  - La decisión de selección vive en una **activity** (`select_issue_activity`) que aplica las reglas puras de `domain/issue_selection.py`. La activity no hace I/O: el resultado queda en el historial de Temporal (replayable, trazable, resumable).
  - Correlación y razones de bloqueo se persisten en dos lugares:
    1. **Ledger de auditoría JSONL append-only** (`persistence/audit.py`, puerto `AuditSink`): una línea por *delivery*, idempotente por `event_delivery_id` (los reintentos nunca duplican líneas). PostgreSQL/Alembic lo sustituirá más adelante sin cambiar el puerto.
    2. **Memo del workflow** (`workflow.upsert_memo`): `issue_id`, `repository`, `workflow_state`, `blocking_reasons` — se actualiza tras la activity de auditoría; una issue no seleccionable (Done/Canceled/no aprobada) termina en `BLOCKED`, sigue siendo trazable y no ejecuta ningún trabajo.
  - Reintentos y time-outs: las activities llevan `RetryPolicy` explícita (selección: 3 intentos; auditoría: 5) y `start_to_close_timeout` por actividad. Un fallo transitorio del sink se absorbe reintento a reintento sin duplicar auditoría (el sink es idempotente por delivery).
  - Idempotencia de extremo a extremo: **dedupe de edge** (`persistence/idempotency.py`, TTL configurable, key `Linear-Delivery` o hash del body si falta la cabecera) más **reutilización del workflow id** en Temporal (durable). Si el edge libera el claim (fallo de start o de configuración), Linear puede reintentar y repetir el procesado de forma segura.
- **Consecuencias:** el cuerpo del workflow sigue sin I/O (cumple ADR-0002). Un solo fichero de auditoría por despliegue. La construcción de `ApprovedTaskSpec` (objetivo y criterios de la issue) llega con la planificación (H2); hoy el workflow termina en `READY` tras dejar registrada la selección.
