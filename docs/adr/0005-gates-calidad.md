# ADR-0005: Gates de calidad: Ruff, mypy strict y cobertura per-file 100/80/0

- **Estado:** Aceptado (GEN-17 + GEN-14)
- **Contexto:** Los agentes de código generan volumen; sin gates automáticos la calidad decae y las partes críticas quedan sin verificar detrás de medias globales.
- **Decisión:**
  - **Ruff** como linter/analizador (reglas E, W, F, I, UP, B, SIM, RUF, ASYNC, S) con `per-file-ignores` mínimos en tests.
  - **mypy `strict = true`** sobre `src/` y `scripts/`.
  - **pytest** con markers `temporal` e `integration`; `asyncio_mode = auto`.
  - **Cobertura por archivo** (CORE 100 líneas+ramas, IMPORTANT 80, INFRA 0) validada por `scripts/check_coverage.py`; ejecución en CI como paso bloqueante.
- **Consecuencias:** Ninguna PR mergeable con gates rojos; los umbrales se cambian solo vía ADR. La evidencia de TDD (RED/GREEN) se documenta en `docs/evidence/`.
- **Nota:** los hooks locales (pre-commit/pre-push) de GEN-14 quedan pendientes de una issue futura; el gate real hoy es CI.
