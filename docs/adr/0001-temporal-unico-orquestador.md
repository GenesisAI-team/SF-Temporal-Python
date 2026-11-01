# ADR-0001: Temporal es el único orquestador

- **Estado:** Aceptado (GEN-17)
- **Contexto:** La factory necesita estados duraderos, reintentos, esperas largas (espera de merge humano) y coordinación de fases (planning → coding → verification → review → PR).
- **Decisión:** Usar el **Temporal Python SDK** (`temporalio`) como único motor de orquestación. Prohibido introducir LangGraph, BullMQ, Celery, Airflow u otra capa de control (quiebra la trazabilidad y duplica máquinas de estado).
- **Consecuencias:**
  - Los estados de ejecución viven en el historial de Temporal; PostgreSQL queda reservado para auditoría/metadatos (H1+).
  - El worker es el único proceso que ejecuta workflows y activities.
  - Requiere determinismo estricto (ver ADR-0002) y pruebas con `temporalio.testing`.
- **Alternativas descartadas:** LangGraph.js/TS (variante de GEN-16, otro repo), BullMQ+Redis (cola, no orquestador de estados), timers propios (reimplementan mal lo que Temporal ya resuelve).
