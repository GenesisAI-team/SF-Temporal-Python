# Catálogo de skills — SF-Temporal-Python

> GEN-17: en el bootstrap **solo** se define el catálogo, las políticas de
> versiones y la estructura. La instalación/adaptación de skills es por issues
> posteriores, una a una, con verificación.

## Política de incorporación

Antes de añadir una skill externa a este repositorio:

1. **Procedencia:** repositorio oficial y autor identificable.
2. **Licencia:** compatible con uso en repositorio privado (registrar SPDX).
3. **Contenido:** leer el `SKILL.md` completo; sin scripts opacos ni exfiltración.
4. **Función:** debe cubrir una etapa concreta de nuestro workflow (spec, tdd, review…), no "por si acaso".
5. **Versión:** fijar por commit/tag; registrar fecha y revisor en este catálogo.
6. **Aprobación humana** antes de merge.

Directorios: `skills/external/` (copias verificadas) y `skills/custom/` (propias). Ambos vacíos hoy a propósito.

## Skills públicas de referencia — [mattpocock/skills](https://github.com/mattpocock/skills)

| Skill | Propósito (según catálogo público) | Estado en este repo |
| --- | --- | --- |
| `setup-matt-pocock-skills` | Instalador del set | No instalada |
| `grill-me` | Interrogar el requisito antes de especificar | No instalada (proceso actual por ChatGPT) |
| `grill-with-docs` | Grill apoyado en documentación | No instalada |
| `to-spec` | Convertir requisito en especificación | No instalada |
| `to-tickets` | Convertir spec en tickets | No instalada |
| `research` | Investigación dirigida | No instalada |
| `domain-modeling` | Modelado de dominio | No instalada |
| `codebase-design` | Diseño de código existente | No instalada |
| `tdd` | Ciclo RED/GREEN/REFACTOR | No instalada (regla ya obligatoria por AGENTS.md) |
| `implement` | Implementación guiada | No instalada |
| `diagnosing-bugs` | Diagnóstico de fallos | No instalada |
| `code-review` | Revisión de código | No instalada |
| `pr` | Preparación de PR | No instalada |
| `retro` | Retrospectiva | No instalada |

## Skills públicas — [540/agentic-toolbox](https://github.com/540/agentic-toolbox)

| Skill | Propósito | Estado |
| --- | --- | --- |
| `gauntlet-audit` | Auditoría exhaustiva | No instalada |
| `explain-pr` | Explicación de PRs | No instalada |

**Nota (GEN-17):** no asumir que todas las skills internas de 540 están publicadas.

## Skills propias previstas (desarrollo por issues posteriores)

| Skill | Hito previsto | Estado |
| --- | --- | --- |
| `plan-implementation` | H1–H2 | Pendiente |
| `verify-acceptance` | H3 | Pendiente |
| `review-risk` | H3 | Pendiente |
| `repair-failure` | H3 | Pendiente |
| `browser-qa` | H3+ | Pendiente |
| `detect-spec-drift` | H3 | Pendiente |
| `review-migration` | H4+ | Pendiente |

## Registro de incorporaciones

| Fecha | Skill | Versión/commit | Licencia | Revisor | PR |
| --- | --- | --- | --- | --- | --- |
| — | — | — | — | — | — |

(Entradas vacías: ninguna skill externa instalada todavía.)
