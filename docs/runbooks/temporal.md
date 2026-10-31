# Runbook — stack Temporal local

## Composición (`infrastructure/docker/compose.yaml`)

| Servicio | Imagen | Puerto | Función |
| --- | --- | --- | --- |
| `postgres` | `postgres:16-alpine` | — (interno 5432) | Persistencia del servidor (dev) |
| `temporal` | `temporalio/auto-setup:1.29.7` | 7233 (gRPC) | Servidor Temporal; crea el esquema al arrancar |
| `temporal-ui` | `temporalio/ui:2.57.0` | 8233 (HTTP) | UI de inspección |

Credenciales de desarrollo `temporal/temporal`: **solo** para esta base local; nunca reutilizar fuera de este compose.

## Operación

```bash
docker compose -f infrastructure/docker/compose.yaml up -d --wait
docker compose -f infrastructure/docker/compose.yaml ps
docker compose -f infrastructure/docker/compose.yaml logs temporal --tail 50
docker compose -f infrastructure/docker/compose.yaml down        # conserva el volumen
docker compose -f infrastructure/docker/compose.yaml down -v     # borra el volumen
```

## Verificación desde la aplicación

El test de integración conecta con `localhost:7233` (variable `SF_TEMPORAL_ADDRESS`) y ejecuta `SmokeWorkflow` con el worker real:

```bash
uv run pytest tests/integration -m integration -v
```

En la UI (http://localhost:8233) deben aparecer ejecuciones de `SmokeWorkflow` con sus activities `echo_activity`.

## Versionado de imágenes

Las imágenes están **fijadas por versión** en el compose (no `latest`) para reproducibilidad. Subir de versión = PR que actualiza el compose + evidencia de la suite de integración en verde.
