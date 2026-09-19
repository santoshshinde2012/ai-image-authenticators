# Naming conventions

Short rules for this repository. See also [contributing.md](./contributing.md).

## Documentation & articles

| Kind | Convention | Examples |
|---|---|---|
| Docs Markdown | `kebab-case.md` | `architecture.md`, `system-design.md`, `naming-conventions.md` |
| Docs index | `docs/README.md` | replaces a separate `DOC_INDEX.md` |
| Doc diagrams | `kebab-case.drawio` | `docs/diagrams/layering.drawio` (exports to `docs/assets/layering.png`) |

## Scripts

| Kind | Convention | Examples |
|---|---|---|
| Shell | `kebab-case.sh` | `run-api.sh`, `run-dev.sh` |
| Python | `snake_case.py` | `run_local_benchmark.py` |

## Python & TypeScript

| Kind | Convention |
|---|---|
| Python modules/packages | `snake_case` |
| Python classes | `PascalCase` |
| Python functions / vars | `snake_case` |
| Analyzer `id` keys (API contract) | stable `snake_case` — do **not** rename (`local_corr`, `srm`, …) |
| React components | `PascalCase` filenames |
| CSS files | `kebab-case` |
| TS modules | `camelCase` |

Optional: module file `local_corr.py` may be renamed to `local_correlation.py` only if imports are updated and the analyzer id remains `local_corr`.

## Layout

- Canonical API: `apps/api` (no legacy top-level `backend/` tree).
  `scripts/export_drawio_diagrams.py` renders each to the sibling `assets/*.png` with the source embedded
  in the PNG. Sources and PNGs are both committed, and Markdown references the PNGs (no mermaid).
