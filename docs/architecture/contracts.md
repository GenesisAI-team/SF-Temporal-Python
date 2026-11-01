# Contratos iniciales

## ApprovedTaskSpec (`contracts/approved_task.py`)

Contrato inmutable (`frozen=True`) de una especificación aprobada por un humano. Es lo que la factory (H1+) recibirá del webhook/planificación.

| Campo | Tipo | Regla |
| --- | --- | --- |
| `issue_id` | `str` | formato exacto `GEN-\d+` |
| `spec_version` | `int` | ≥ 1; cambia cuando se reaprueba la spec |
| `repository` | `str` | `owner/name` |
| `base_branch` | `str` | defecto `main` |
| `objective` | `str` | no vacío |
| `acceptance_criteria` | `list[str]` | ≥ 1, sin blancos |
| `dependencies` | `list[str]` | cada una formato `GEN-N` |
| `exclusions` | `list[str]` | sin blancos |
| `constraints` | `list[str]` | sin blancos |

## IssueWorkflowState (`contracts/workflow_state.py`)

Estados documentados del futuro `IssueWorkflow` (H1):

`READY → PREPARING → PLANNING → IMPLEMENTING → VERIFYING → REVIEWING → PR_READY → AWAITING_MERGE → DONE`
Excepcionales: `REPAIRING`, `BLOCKED`, `CANCELLED`.

Los valores están congelados por test (`test_workflow_state_values_are_stable`); añadir o renombrar estados exige cambiar el test y justificarlo en la PR.

## Contratos Temporal (bootstrap)

- `EchoInput` (dataclass frozen) — entrada de `echo_activity`; lleva `workflow_id` para trazabilidad/idempotencia futura.
- `SmokeWorkflow.run(message: str) -> list[str]` — salida de la demo.

## Regla

Nueva frontera de datos = nuevo contrato en `contracts/` + test primero. Los workflows no deben intercambiar dicts ad-hoc.
