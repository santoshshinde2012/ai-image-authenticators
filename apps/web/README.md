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

Package name: `ai-image-authenticator-web` (not a leftover `frontend/` app).
