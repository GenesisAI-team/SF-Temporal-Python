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

## Contratos H1 (GEN-38, ADR-0006/0007)

- `IssueSelectionCriteria` (frozen) — estados seleccionables + repositorios permitidos (validados por reglas de `domain/`).
- `IssueSnapshot` (frozen) — vista de una issue extraída de un evento Linear ya firmado; métodos tolerantes (blank state/foreign id bloquean en el selector, no en el parse).
- `IssueWorkflowInput` / `SelectIssueResult` / `IssueWorkflowResult` / `WorkflowStartResult` (dataclasses frozen, `contracts/workflow_io.py`) — frontera con el SDK Temporal: la conversión por defecto de temporalio serializa dataclasses, mientras los contratos Pydantic hacen la validación de cara a la API. Un issue create/recover so run id `issue-<GEN-N>`.
- `WorkflowRunCorrelation` (frozen) — línea de auditoría por delivery: correlación issue/repositorio/workflow, resultado de selección, razones de bloqueo, ids de run (None cuando el bloqueo ocurre antes del workflow).

## Regla

Nueva frontera de datos = nuevo contrato en `contracts/` + test primero. Los workflows no deben intercambiar dicts ad-hoc.
