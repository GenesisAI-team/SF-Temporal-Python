# Evidencia TDD — GEN-17 (bootstrap)

Registro de ciclos RED → GREEN → REFACTOR ejecutados en la rama
`feat/GEN-17-bootstrap-temporal-python`. Salidas reales de pytest.

| Ciclo | Test | RED (razón correcta) | GREEN | Notas |
| --- | --- | --- | --- | --- |
| C1 Config | `test_settings.py` (3 tests) | `ModuleNotFoundError: No module named 'super_factory.config.settings'` | 3 passed | — |
| C2/C3 Dominio | `test_task_spec.py` (12 tests) | `ModuleNotFoundError` (implementación retirada para el registro) | incluido en 31 passed | — |
| C2/C3 Contratos | `test_contracts.py` (11 tests) | `ModuleNotFoundError: super_factory.contracts.approved_task` | 31 passed (suite unit) | — |
| C4 Estados | `test_workflow_state.py` | *Sin RED previa*: enum declarativo escrito con su test | 1 passed | Desviación documentada: declaración de datos, sin lógica |
| C5/C6 API | `test_api.py` | `ImportError: super_factory.api.app` | 34 passed | REFACTOR: `TestClient` → `httpx.ASGITransport` (deprecación Starlette→httpx2); 35 passed sin warnings |
| C7/C8 Temporal | `test_smoke_workflow.py` | colección: módulos workflow/activity inexistentes | 1er intento: **2 failed** (`ValueError: Activity echo_activity is not async so an activity_executor must be present`) → fix real: activity async → **39 passed** | Incluye time-skipping + `Replayer` |
| C9 Worker | `test_queues.py`, `test_worker.py` | `ModuleNotFoundError` (queues, factory_worker) | 44 passed | `Worker.task_queue` verificado en runtime del SDK 1.35.0 |
| C10 Cobertura | `test_check_coverage.py` (8 tests) | `ModuleNotFoundError: scripts.check_coverage` | 54 passed | Gate real ejecutado: 1ª ejecución **exit 1** con violaciones reales (esquema JSON de coverage: `percent_covered`, no `percent_lines`) → lector corregido a cálculo desde conteos → **exit 0**. 2 tests del gate fallaron por redondeo de datos simulados → corregidos |
| C11 Integración | `test_worker_roundtrip.py` | — (requiere servidor) | **PASSED (2.12 s)** contra Temporal real (compose: postgres 16 + auto-setup 1.29.7 + ui 2.57.0) | Worker `run_worker()` + `SmokeWorkflow` + historial verificado |

## Gates finales (última ejecución)

```text
ruff check .        → All checks passed!
mypy src            → Success: no issues found in 29 source files
pytest unit+temporal → 54 passed
check_coverage      → coverage policy OK (per-file 100/80), exit 0
pytest integration  → 1 passed (workflow real completado en Temporal local)
```

## Evidencia de CI (GitHub Actions, PR #1)

| Run | Resultado | Motivo |
| --- | --- | --- |
| 41223427645 | fail (3–4 s) | `astral-sh/setup-uv@v10` no existe como tag flotante → fijado a `v10.3.3` |
| 41223500812 | fail (47 s) | `Namespace default is not found` (auto-setup registra el namespace de forma asíncrona) → reintento de conexión |
| 41223738948 | fail (46 s) | `Client.connect` no valida el namespace en SDK 1.35; el fallo se movió a `start_workflow_execution` → sonda namespace-scoped con `list_workflows` |
| **41223964791** | **pass** | `quality` 14 s + `integration` 42 s (compose + test de integración real en Linux) |

## Limitación de plataforma registrada

Branch protection y rulesets devuelven **HTTP 403** en repos privados del plan
Free ("Upgrade to GitHub Pro or make this repository public"). La protección de
`main` queda **operativa** (ver AGENTS.md) a la espera de decisión del
propietario (upgrade, repo público o guardarraíl operativo).

## Cobertura por archivo (informe real, cobertura.py branch mode)

- CORE (`domain/task_spec.py`, `contracts/approved_task.py`, `temporal/workflows/smoke.py`): **100 % líneas y ramas**.
- IMPORTANT (config, api, activities, builder): **100 %** en todos los archivos listados en `scripts/check_coverage.py`.
- INFRA: `temporal/workers/run.py` (entrypoint, 0 % exigido) y `queues.py` (constantes).
- Total del suite unit+temporal: 92,3 % líneas con ramas activas; la política per-file es el gate, no la media.
