# ADR-0003: Contratos Pydantic inmutables como frontera entre capas

- **Estado:** Aceptado (GEN-17)
- **Contexto:** Las capas (API, workflows, agentes, integraciones) intercambian datos que deben validarse y versionarse; la especificación aprobada por un humano debe poder detectarse como "drift" más adelante (H3).
- **Decisión:**
  - Los contratos viven en `src/super_factory/contracts/` como modelos Pydantic **`frozen=True`** (inmutables).
  - `ApprovedTaskSpec` porta: `issue_id` (`GEN-N`), `spec_version`, `repository`, `base_branch`, `objective`, `acceptance_criteria` (no vacío), `dependencies`, `exclusions`, `constraints`.
  - Las reglas de validación puras (formato de issue ID, no-vacíos) viven en `domain/` y se invocan desde los validadores de los contratos.
- **Consecuencias:** Cualquier cambio de contrato exige test primero; los workflows reciben/ devuelven solo contratos o dataclasses serializables.
- **Relación:** `IssueWorkflowState` (contracts/workflow_state.py) documenta los estados futuros de H1; su transición real se implementará allí, no aquí.
