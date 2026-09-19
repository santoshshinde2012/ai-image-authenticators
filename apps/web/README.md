# AI Image Authenticator — Web (`apps/web`)

Vite + React + TypeScript UI for the local forensic examiner.

## Layout

```
src/
  app/                  # App shell (main.tsx, App.tsx)
  features/analysis/    # api.ts, types.ts, components/*
  shared/styles/        # global CSS / Tailwind entry
  assets/
```

## Scripts

```bash
npm ci
npm run dev      # http://127.0.0.1:5173 (proxies /api → :8000)
npm run build    # tsc -b && vite build → dist/
npm run lint     # oxlint
```

API contracts live under `/api/v1`. Types in `features/analysis/types.ts` mirror `interfaces/http/schemas.py` (verdict bands, `evidence_paths`, analyzer signal cards).

## Benchmark snapshot

The single-page UI includes a Chart.js chart of local regression fixture scores and a downloadable PNG with the method caveat. Run `uv run python scripts/run_local_benchmark.py` from the repository root to refresh `src/features/analysis/benchmark_summary.json`, then rebuild the web app. The chart describes the recorded outputs of a small local fixture set; it is not an accuracy estimate.

Package name: `ai-image-authenticator-web` (not a leftover `frontend/` app).
