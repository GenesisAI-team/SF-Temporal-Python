# ADR-0004: Task queues y workers separados lógicamente

- **Estado:** Aceptado (GEN-17)
- **Contexto:** La factory ejecuta orquestación, código generado (agentes), verificación e integraciones con riesgos y costes distintos. Mezclarlo en una cola impide escalar y aplicar guardarraíles por fase.
- **Decisión:** Cuatro task queues nombradas en `temporal/workers/queues.py`:
  - `factory-orchestration` — workflows de issue/épica (worker actual).
  - `factory-coding` — actividades de agentes de código (H2).
  - `factory-verification` — tests, lint, análisis (H3).
  - `factory-integrations` — Linear, GitHub, webhooks (H1+).
- **Registro central:** `build_worker()` en `temporal/workers/factory_worker.py` es el único punto de registro de workflows/activities (probado en tests unitarios y de integración).
- **Consecuencias:** Un proceso worker por cola (o rol); las activities pueden moverse de cola sin tocar el workflow. El bootstrap solo implementa la cola de orquestación; las demás existen como constantes documentadas.
