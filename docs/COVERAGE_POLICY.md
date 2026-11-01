# Política de cobertura — 100/80/0 per-file

Fuente: GEN-14 (política de coverage honesta) aplicada a SF-Temporal-Python según GEN-17.
Principio: **no usar medias globales** para ocultar partes críticas sin verificar.

## Niveles

| Nivel | Umbral | Criterio de asignación | Archivos actuales |
| --- | --- | --- | --- |
| **CORE** | 100 % líneas y ramas | Reglas de negocio puras y determinismo de workflows | `domain/task_spec.py`, `contracts/approved_task.py`, `temporal/workflows/smoke.py` |
| **IMPORTANT** | 80 % líneas y ramas | Orquestación, API, adaptadores y builders testeables | `config/settings.py`, `api/app.py`, `api/routes/health.py`, `api/webhooks/linear.py`, `temporal/activities/smoke.py`, `temporal/workers/factory_worker.py` |
| **INFRA** | 0 % exigido | Constantes, entrypoints de proceso, `__init__.py` | `temporal/workers/queues.py`, `temporal/workers/run.py`, todos los `__init__.py` |

Reglas:

- Un archivo INFRA **no puede contener reglas activas de negocio**; si las tiene, sube de nivel.
- El validador **falla** si un archivo CORE/IMPORTANT no aparece medido (archivos ocultos = violación).
- `__init__.py` se omiten de la medición (declarativos).
- No escribir tests vacíos para subir porcentajes.

## Cómo se aplica

```bash
uv run coverage run -m pytest tests/unit tests/temporal -q
uv run coverage combine
uv run coverage json -o coverage.json
uv run python -m scripts.check_coverage   # exit 1 si hay violaciones
```

El gate corre en CI (job `quality`) y debe pasar antes del merge.

## Evolución

Al añadir módulos nuevos (H1+), clasificarlos explícitamente en
`scripts/check_coverage.py` (`CORE_FILES` / `IMPORTANT_FILES`) en la misma PR
que los introduce. Cambiar un umbral requiere ADR.
