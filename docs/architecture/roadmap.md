# Roadmap — hitos de la Software Factory

> Cada hito es una o varias issues de Linear, aprobadas por separado.
> Nada de este documento se implementa sin issue correspondiente.

| Hito | Entrega | Depende de |
| --- | --- | --- |
| **H1** | Linear + FastAPI + Temporal: arrancar `IssueWorkflow` real desde una issue aprobada (webhook firmado, idempotencia, estados) | Bootstrap (GEN-17) |
| **H2** | Codex + Docker sandbox + GitHub: generar rama y PR desde una issue | H1 |
| **H3** | Quality gates avanzados, revisión independiente, repair loops, detección de spec drift | H2 |
| **H4** | EpicWorkflow: child workflows, dependencias, concurrencia controlada, desbloqueo tras merge | H1 (+ H2 preferible) |
| **H5** | Observabilidad, control de costes, seguridad, evals (Promptfoo), dashboard | H2+ |

## Backlog técnico detectado en el bootstrap (candidato a issues)

- Hooks locales pre-commit/pre-push (GEN-14 estilo) — hoy el gate es CI.
- Firma y validación real de webhooks Linear.
- Persistencia de auditoría (PostgreSQL + Alembic).
- GitHub App con permisos mínimos (en lugar de tokens personales).
- Actualización del documento del protocolo en Linear para incluir TDD/cobertura/AGENTS.md (hoy viven en GEN-14/GEN-16/este repo).
- Añadir `SF-Temporal-Python` a los repositorios vinculados del protocolo.
