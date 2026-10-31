# AGENTS.md — Reglas para agentes de código en SF-Temporal-Python

> Fuente de verdad: issue **GEN-17** (Linear, proyecto Ultimate Coding) + el
> [Protocolo de trabajo — Ultimate Coding](https://linear.app/genesisnavarra/document/protocolo-de-trabajo-ultimate-coding-chatgpt-codex-y-opencode-12e289b81826).
> Las reglas de ingeniería de este archivo provienen de GEN-17, GEN-14 y GEN-16
> (el documento del protocolo operativo no las contiene; queda registrado aquí).

## Flujo de trabajo (obligatorio)

- Linear es la fuente de verdad. **Una issue → un repositorio → una rama → una PR.**
- Rama: `feat|fix|refactor|chore|docs|perf/GEN-N-descripcion` (minúsculas, sin acentos).
- Estados: `Todo` → `In Progress` (al empezar) → `In Review` (PR abierta) → `Done` (tras merge y verificación). Nunca Backlog.
- Nunca push directo a `main`. Nunca merge automático. El merge lo ejecuta **un humano**.
- No ampliar alcance sin reflejarlo en Linear. No empezar una issue sin leerla completa.

## TDD (obligatorio para lógica nueva)

1. **RED**: escribe el test del comportamiento esperado; ejecútalo y confirma que falla **por la razón correcta**.
2. **GREEN**: implementa el mínimo necesario para que pase.
3. **REFACTOR**: mejora diseño sin cambiar comportamiento; suite completa en verde.
4. No escribas toda la implementación para añadir tests después. No afirmes verde sin ejecutar. Commits normales solo con pruebas verdes.

## Cobertura — política per-file 100/80/0 (sin medias globales)

| Nivel | Umbral | Dónde |
| --- | --- | --- |
| CORE | 100 % líneas **y** ramas | `domain/`, `contracts/`, `temporal/workflows/` |
| IMPORTANT | 80 % líneas y ramas | `config/`, `api/`, `temporal/activities/`, builders |
| INFRA | 0 % exigido | constantes y entrypoints (sin excluir reglas activas) |

La política se aplica con `scripts/check_coverage.py` (falla si un archivo crítico no se midió).
Detalle en `docs/COVERAGE_POLICY.md`.

## Comandos de verificación (ejecutar y mostrar resultados)

```bash
uv sync --frozen
uv run ruff check .
uv run mypy src
uv run pytest tests/unit tests/temporal -q
uv run coverage run -m pytest tests/unit tests/temporal -q && uv run coverage combine \
  && uv run coverage json -o coverage.json && uv run python -m scripts.check_coverage
# integración (requiere el stack local):
docker compose -f infrastructure/docker/compose.yaml up -d --wait
uv run pytest tests/integration -m integration -v
```

## Arquitectura (inviolable sin ADR nuevo)

- **Temporal es el único orquestador.** Prohibido LangGraph, BullMQ u otra capa de control.
- Los **Workflows son deterministas**: sin red, shell, Docker, fechas reales ni modelos. Todo efecto vive en **Activities**.
- Actividades idempotentes; timeouts y `heartbeat` en operaciones largas; reintentos técnicos separados de correcciones funcionales.
- Los módulos marcados PENDIENTE (H1+) no deben simularse: devolver errores explícitos (p. ej. 501) o no implementarse.
- Contratos entre capas: Pydantic en `src/super_factory/contracts/`. Inmutables (`frozen=True`).

## Seguridad y guardarraíles

- Nunca commitear `.env`, tokens, claves ni credenciales. `.env.example` sin secretos.
- El agente **jamás** hace merge, no tiene permisos de administración en producción y no ejecuta código de agentes en el host productivo.
- Webhooks firmados y validados (H1+); idempotencia frente a duplicados.
- Guardar evidencias reales: comandos, exit codes, salidas. No confiar en afirmaciones sin ejecución.

## Decisiones arquitectónicas

Registrar toda decisión significativa en `docs/adr/` con ADR incrementado. Las decisiones ya registradas (0001–0005) son vinculantes.

## Skills

Catálogo en `docs/skills/CATALOG.md`. No instalar skills externas sin verificar procedencia, licencia y funcionalidad dentro del workflow. El desarrollo de skills propias es por issues posteriores.

## Windows / entorno local

- Python gestionado por `uv` (3.12 fijado en `.python-version`).
- Temporal local: Docker Compose (`infrastructure/docker/compose.yaml`); UI en http://localhost:8233.
- Worker: `uv run python -m super_factory.temporal.workers.run`
