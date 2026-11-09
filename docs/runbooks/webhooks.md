# Runbook — Webhook Linear firmado (H1, GEN-38)

## Configuración (`.env`, nunca en el repo)

```bash
SF_LINEAR_WEBHOOK_SECRET=<secreto del webhook, Linear -> Settings -> API -> Webhooks>
SF_LINEAR_TARGET_REPOSITORY=GenesisAI-team/SF-Temporal-Python
SF_LINEAR_SELECTABLE_STATES=Todo,In Progress
SF_LINEAR_TIMESTAMP_TOLERANCE_SECONDS=60   # ampliable (p. ej. 22000) para tolerar reintentos de Linear
SF_LINEAR_DEDUPE_TTL_SECONDS=86400         # mayor que la ventana de reintentos documentada (6 h)
SF_AUDIT_LOG_PATH=var/audit/events.jsonl
SF_TEMPORAL_ADDRESS=localhost:7233
```

Criterios de selección (reglas puras en `domain/issue_selection.py`): la issue debe tener identificador `GEN-N`, su estado debe estar en `SF_LINEAR_SELECTABLE_STATES` (Done, Canceled, Backlog, etc. quedan bloqueados con razones auditables) y el repositorio objetivo debe estar configurado en formato `owner/name` y permitido.

## Arranque local (stack completo)

```bash
docker compose -f infrastructure/docker/compose.yaml up -d --wait
uv run python -m super_factory.temporal.workers.run        # worker con IssueWorkflow registrado
SF_LINEAR_WEBHOOK_SECRET=<secreto> uv run uvicorn super_factory.api.app:create_app --factory --port 8000
```

Con el stack arriba y las variables definidas, al mover una issue del equipo a `Todo` en Linear (o usando el smoke de abajo) aparece en la UI de Temporal (http://localhost:8233) el run `issue-<GEN-N>` con las activities `select_issue_activity` y `record_audit_activity`, y el memo con `issue_id`, `repository`, `workflow_state` y `blocking_reasons`.

## Smoke con firma (sin Linear real)

```bash
uv run python -m scripts.smoke_linear_webhook \
  --url http://localhost:8000/webhooks/linear \
  --secret "lin_wh_..." \
  --issue GEN-38 \
  --state Todo
```

El script construye el payload de ejemplo, calcula la firma HMAC-SHA256 (hex) sobre el body exacto y la envía en la cabecera `Linear-Signature`, junto a un `Linear-Delivery` aleatorio. Respuestas posibles: `accepted`, `recovered` (el run ya existía), `duplicate` (mismo delivery reenviado), `ignored` (evento no Issue), `blocked` (issue no seleccionable); errores: `401` firma, `400` payload inválido o stale, `500` configuración inválida o dispatch fallado, `503` secreto ausente.

## Verificación de auditoría e idempotencia

```bash
tail -n 5 var/audit/events.jsonl
```

- Una línea por delivery (`SELECTED`/`BLOCKED`); repetir el mismo `Linear-Delivery` no añade líneas.
- Razones de bloqueo visibles: `STATE_NOT_SELECTABLE: Done`, `REPOSITORY_UNRESOLVED`, `REPOSITORY_MALFORMED: ...`, `REPOSITORY_NOT_ALLOWED: ...`, `ISSUE_ID_MALFORMED: ENG-...`.

## Diagnóstico rápido

| Síntoma | Causa probable |
| --- | --- |
| 401 en cada entrega | `SF_LINEAR_WEBHOOK_SECRET` distinto del secreto de Linear |
| 400 stale sistemáticos | tolerancia 60 s con reloj desfasado; ampliar `SF_LINEAR_TIMESTAMP_TOLERANCE_SECONDS` |
| 200 duplicate sin run nuevo | delivery repetido (esperado); revisar `SF_LINEAR_DEDUPE_TTL_SECONDS` |
| 503 webhook secret not configured | falta la variable en el proceso |
| 500 invalid configuration | repositorio objetivo vacío o sin formato `owner/name` |
| 500 workflow dispatch failed | Temporal caído; levantar compose y worker |
