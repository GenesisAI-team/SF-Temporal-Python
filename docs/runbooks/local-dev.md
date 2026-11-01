# Runbook — desarrollo local

## Requisitos

- [uv](https://docs.astral.sh/uv/) (gestiona Python 3.12 según `.python-version`)
- Docker Desktop (solo para Temporal local e integración)

## Puesta en marcha

```bash
git clone https://github.com/GenesisAI-team/SF-Temporal-Python.git
cd SF-Temporal-Python
uv sync --frozen
cp .env.example .env   # opcional; los defaults funcionan en local
```

## Comandos diarios

```bash
uv run pytest tests/unit tests/temporal -q    # suite rápida (usa time-skipping, no necesita Docker)
uv run ruff check .                           # lint
uv run mypy src                               # tipos
uv run pytest tests/integration -m integration -v   # requiere el stack de Temporal
```

## Temporal local

```bash
docker compose -f infrastructure/docker/compose.yaml up -d --wait
# UI: http://localhost:8233   gRPC: localhost:7233
uv run python -m super_factory.temporal.workers.run   # worker (Ctrl+C para parar)
docker compose -f infrastructure/docker/compose.yaml down     # parar (conserva datos)
docker compose -f infrastructure/docker/compose.yaml down -v  # parar y limpiar datos
```

## Coverage completo (igual que CI)

```bash
uv run coverage run -m pytest tests/unit tests/temporal -q
uv run coverage combine
uv run coverage json -o coverage.json
uv run python -m scripts.check_coverage
```

## Problemas conocidos

- **`uv` no se encuentra en una terminal nueva:** reabrir la terminal (el PATH de usuario se actualizó al instalar).
- **El test de integración falla con timeout:** el stack de Temporal no está levantado o sigue arrancando; comprueba `docker compose ps` y los logs de `docker-temporal-1`.
- **Puerto 7233/8233 ocupado:** para el servicio conflicto o cambia el mapeo del compose (solo local).
