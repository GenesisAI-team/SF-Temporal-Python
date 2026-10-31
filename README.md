# SF-Temporal-Python

**Software Factory orquestada con Temporal (Python)** — transforma tareas aprobadas en Linear en Pull Requests verificadas de GitHub.

> **Estado:** bootstrap (GEN-17). Repositorio fundacional. La factory completa (Linear → agentes → PR) se construirá en issues posteriores (H1–H5).
>
> **Propiedad:** privado, uso interno de GenesisAI-team. Sin licencia de código abierto.

## Stack

| Área | Elección |
| --- | --- |
| Lenguaje | Python 3.12 |
| Gestión de entorno | [uv](https://docs.astral.sh/uv/) |
| API | FastAPI + Pydantic |
| Orquestación | Temporal Python SDK (`temporalio`) |
| Pruebas | pytest, `temporalio.testing` |
| Calidad | Ruff, mypy (strict) |
| CI | GitHub Actions |
| Temporal local | Docker Compose (PostgreSQL + server + UI) |

## Requisitos

- [uv](https://docs.astral.sh/uv/getting-started/installation/) (gestiona Python 3.12 automáticamente)
- Docker Desktop (para Temporal local)

## Comandos básicos

```bash
uv sync --frozen        # instalar dependencias exactas de uv.lock
uv run pytest           # tests unitarios y de Temporal (time-skipping, sin Docker)
uv run ruff check .     # lint
uv run mypy src         # tipos

# Temporal local (ver docs/runbooks/temporal.md)
docker compose -f infrastructure/docker/compose.yaml up -d --wait   # UI en http://localhost:8233
uv run python -m super_factory.temporal.workers.run                 # worker
uv run pytest tests/integration -m integration -v                   # integración vs servidor real

# Gates de cobertura (igual que CI)
uv run coverage run -m pytest tests/unit tests/temporal -q
uv run coverage combine && uv run coverage json -o coverage.json
uv run python -m scripts.check_coverage
```

## Estructura

```text
src/super_factory/   # api, config, contracts, domain, temporal, agents, sandbox,
                     # integrations, verification, persistence, observability
tests/               # unit, temporal, integration
infrastructure/      # docker (compose de Temporal local), temporal
docs/                # architecture, adr, runbooks, skills, evidence
skills/              # external, custom (catálogo; instalación por issues posteriores)
```

## Documentación

- `AGENTS.md` — reglas para agentes de código (TDD, gates, ramas, seguridad)
- `docs/architecture/` — arquitectura y roadmap
- `docs/adr/` — decisiones arquitectónicas registradas
- `docs/runbooks/` — guías de operación local
- `docs/skills/CATALOG.md` — inventario y estrategia de skills

## Trabajo

Fuente de verdad: issue **GEN-17** en Linear (proyecto Ultimate Coding). Una issue → una rama → una PR. Merge solo con aprobación humana.
