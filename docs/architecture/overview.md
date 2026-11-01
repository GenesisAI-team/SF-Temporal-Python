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

## Implementado hoy (bootstrap)

| Componente | Estado | Dónde |
| --- | --- | --- |
| Config tipada (`SF_*`) | ✅ | `config/settings.py` |
| Contrato `ApprovedTaskSpec` + estados | ✅ | `contracts/` |
| Reglas de dominio (issue ID, criterios) | ✅ | `domain/task_spec.py` |
| FastAPI `/healthz` | ✅ | `api/routes/health.py` |
| Webhook Linear | 🚧 **501 explícito** (H1) | `api/webhooks/linear.py` |
| Workflow mínimo `SmokeWorkflow` | ✅ (demostración) | `temporal/workflows/smoke.py` |
| Worker + 4 task queues | ✅ (solo orquestación activa) | `temporal/workers/` |
| Stack Temporal local | ✅ | `infrastructure/docker/compose.yaml` |
| Gates + CI | ✅ | `scripts/check_coverage.py`, `.github/workflows/ci.yml` |

## Pendiente (issues posteriores — no simulado)

- **H1:** webhooks firmados, `IssueWorkflow` real (estados de `IssueWorkflowState`), persistencia de auditoría.
- **H2:** Codex + Docker sandbox + creación de PRs.
- **H3:** quality gates avanzados, revisión independiente, repair loops.
- **H4:** EpicWorkflow (child workflows, dependencias).
- **H5:** observabilidad, costes, evals, dashboard.

Los paquetes `agents/`, `sandbox/`, `integrations/`, `verification/`, `persistence/`, `observability/` existen vacíos **a propósito**: son marcadores de estructura, no implementaciones.

## Reglas de dependencia entre capas

```text
api → contracts, config, temporal(client)
temporal/workflows → contracts, temporal/activities (imports passthrough)
temporal/activities → domain, contracts, integraciones externas (futuro)
domain → (nada; puro)
contracts → domain (validadores)
```

`domain/` no importa de ningún otro paquete interno.
