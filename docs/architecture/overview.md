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
| Workflow `IssueWorkflow` durable (selección, auditoría, memo; **sin** agentes aún) | ✅ (H1, ADR-0006) | `temporal/workflows/issue.py` |
| Auditoría JSONL + dedupe de deliveries | ✅ (H1) | `persistence/` |
| Adapters Linear + SDK Temporal | ✅ (H1) | `integrations/linear/`, `integrations/temporal_sdk/` |
| Workflow mínimo `SmokeWorkflow` | ✅ (demostración) | `temporal/workflows/smoke.py` |
| Worker + 4 task queues (orquestación activa) | ✅ | `temporal/workers/` |
| Stack Temporal local | ✅ | `infrastructure/docker/compose.yaml` |
| Gates + CI | ✅ | `scripts/check_coverage.py`, `.github/workflows/ci.yml` |

## Pendiente (issues posteriores — no simulado)

- **H2:** `ApprovedTaskSpec` desde la issue aprobada (planificación) + Codex + Docker sandbox + creación de PRs en GitHub.
- **H3:** quality gates avanzados, revisión independiente, repair loops.
- **H4:** EpicWorkflow (child workflows, dependencias).
- **H5:** observabilidad, costes, evals, dashboard.
- Persistencia de auditoría en PostgreSQL (sustituye al ledger JSONL de H1).

Los paquetes `agents/`, `sandbox/`, `verification/`, `observability/` siguen existiendo vacíos **a propósito**: son marcadores de estructura, no implementaciones. En H1 se han implementado `integrations/` (adapters Linear y SDK Temporal) y `persistence/` (auditoría + dedupe).

## Reglas de dependencia entre capas

```text
api → contracts, config, temporal(client)
temporal/workflows → contracts, temporal/activities (imports passthrough)
temporal/activities → domain, contracts, integraciones externas (futuro)
domain → (nada; puro)
contracts → domain (validadores)
```

`domain/` no importa de ningún otro paquete interno.
