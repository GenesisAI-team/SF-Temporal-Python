# Arquitectura — SF-Temporal-Python (bootstrap GEN-17)

## Visión de destino

```text
ChatGPT: grill-me → to-spec → to-tickets → aprobación humana
    ↓
Linear (issues + criterios + estados)
    ↓ webhook firmado (H1)
FastAPI
    ↓ Temporal Client
Temporal Server  ── IssueWorkflow (H1) ── EpicWorkflow (H4)
    ↓
GitHub PR + CI + aprobación y merge humanos
    ↓
Cierre y actualización en Linear
```

## Implementado hoy (bootstrap + H1)

| Componente | Estado | Dónde |
| --- | --- | --- |
| Config tipada (`SF_*`) | ✅ | `config/settings.py` |
| Contrato `ApprovedTaskSpec` + estados | ✅ | `contracts/` |
| Reglas de dominio (issue ID, criterios, repositorios) | ✅ | `domain/` |
| FastAPI `/healthz` | ✅ | `api/routes/health.py` |
| Webhook Linear firmado (firma HMAC, anti-replay, idempotencia, bloqueos auditables) | ✅ (H1, ADR-0007) | `api/webhooks/linear.py` |
| Workflow `IssueWorkflow` durable (selección, auditoría, memo) | ✅ (H1, ADR-0006) | `temporal/workflows/issue.py` |
| **Pipeline de PR H2 dentro de `IssueWorkflow`** (spec aprobada, sandbox Docker efímero, agente aislado, verificación, commit/push, PR GH con idempotencia y presupuesto) | ✅ (H2, ADR-0008) | `temporal/workflows/issue.py`, `temporal/activities/pipeline.py` |
| **H3: gates independientes + revisión separada + repair loop acotado + spec drift** (suite tests/lint/typecheck con evidencia, revisor en sesión propia, `REPAIRING` con presupuesto, drift bloquea) | ✅ (H3, ADR-0009) | `domain/quality.py`, `contracts/quality.py`, `verification/quality_gates.py`, `review/`, `temporal/workflows/issue.py` |
| Puertos/adaptadores de agentes, sandbox, procesos, SCM, verificación y revisión | ✅ (H2/H3) | `agents/`, `sandbox/`, `process/`, `scm/`, `verification/`, `review/`, `planning/` |
| Auditoría JSONL + dedupe de deliveries + libro de runs (presupuesto) | ✅ (H1/H2) | `persistence/` |
| Adapters Linear + SDK Temporal | ✅ (H1) | `integrations/linear/`, `integrations/temporal_sdk/` |
| Workflow mínimo `SmokeWorkflow` | ✅ (demostración) | `temporal/workflows/smoke.py` || Worker + 4 task queues (orquestación activa) | ✅ | `temporal/workers/` |
| Stack Temporal local | ✅ | `infrastructure/docker/compose.yaml` |
| Gates + CI | ✅ | `scripts/check_coverage.py`, `.github/workflows/ci.yml` |

## Pendiente (issues posteriores — no simulado)

- Planificación desde la API de Linear: extraer la spec aprobada de la issue
  (criterios/exclusiones/constraints) reemplazando el fichero aprobado de H2
  (la revisión de H3 ya contrasta contra esa spec).
- **H4:** EpicWorkflow (child workflows, dependencias).
- **H5:** observabilidad, costes, evals, dashboard.
- Persistencia de auditoría en PostgreSQL (sustituye al ledger JSONL de H1/H2).
- Operación real del agente implementador y del revisor con imagen sandbox
  dedicada (los adaptadores existen; H2/H3 los dejan configurado-y-falla-explícito).

El entregable H2 mantiene vacíos `observability/` y no amplia `verification/`
más allá del gate básico: son marcadores para H3/H5. `agents/` y `sandbox/`
ya contienen puertos y adaptadores reales (ADR-0008).

## Reglas de dependencia entre capas

```text
api → contracts, config, temporal(client)
temporal/workflows → contracts, temporal/activities (imports passthrough)
temporal/activities → domain, contracts, integraciones externas (futuro)
domain → (nada; puro)
contracts → domain (validadores)
```

`domain/` no importa de ningún otro paquete interno.
