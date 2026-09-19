# Contributing

## Dev setup

```bash
uv sync --all-groups --extra c2pa   # the extra lets the C2PA signature tests run
cd apps/web && npm ci && cd ../..
cp .env.example .env   # optional
```

Run API + UI:

```bash
./scripts/run-dev.sh
# or separately: ./scripts/run-api.sh  and  cd apps/web && npm run dev
```

Quality gates (also run in CI):

```bash
uv run ruff check apps/api/src apps/api/tests
uv run pytest -q
cd apps/web && npm ci && npm run build
```

## How to add an analyzer (OCP)

1. Create `apps/api/src/ai_image_authenticator/application/analyzers/my_signal.py` implementing the `Analyzer` port (or subclass `BaseAnalyzer`).
2. Give it a stable `id` (snake_case key used in fusion, API, and UI) and human `name`.
3. Register it in `container.build_registry()` via `registry.register(...)`.
4. If it should influence the fused score, add a weight key in `application/services/weights.py` (`DEFAULT_WEIGHTS`; re-exported via `fusion.py`) so the table still sums ~1.0.
5. Export the class from `application/analyzers/__init__.py` when it is part of the public analyzer set.
6. Add a focused unit test under `apps/api/tests/`.
7. Optionally emit a visualization via `ArtifactStore.put(...)` and set `viz_url` on the output (paths use `/api/v1/artifacts/...`).

Do **not** put fusion logic, HTTP concerns, or global mutable state inside the analyzer class.

## Naming conventions

| Kind | Convention |
|---|---|
| Python modules/packages | `snake_case` |
| Classes | `PascalCase` |
| Functions / vars | `snake_case` |
| Constants | `UPPER_SNAKE` |
| Analyzer `id` keys | stable `snake_case` (`metadata`, `provenance`, `labels`, `ela`, …) |
| Evidence paths | `pixel_forensic`, `provenance_contract`, `screenshot_path` |
| C2PA analyzer | class `ProvenanceC2PA`, id `provenance`, display name `Content Credentials (C2PA)` |
| React components | `PascalCase` filenames |
| CSS files | `kebab-case` |
| TS modules | `camelCase` |
| npm package (`apps/web`) | `ai-image-authenticator-web` |

Prefer precise names: `container` (not composition), `ports` (not protocols), `config` (not settings module), `routes` (not routers). Prefer **analyzer** in product/docs code names; the article may still use “witness” as a metaphor for the same twelve signals.

## Pull requests

- Keep changes scoped; preserve the **twelve** existing analyzer behaviors unless intentionally changing product logic.
- Prefer small commits with clear messages.
- Do not commit secrets, `.env`, or `apps/web/dist`


## Script naming

| Kind | Convention | Examples |
|---|---|---|
| Shell | `kebab-case.sh` | `scripts/run-api.sh`, `scripts/run-dev.sh` |
| Python | `snake_case.py` | `scripts/run_local_benchmark.py` |

Docs Markdown uses `kebab-case` (see [naming-conventions.md](./naming-conventions.md)); the docs index lives at [README.md](./README.md).
