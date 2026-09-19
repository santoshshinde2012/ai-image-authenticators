# System design (E2E — matches this repo)

Living design doc for **AI Image Authenticator**. Code paths are authoritative.

## 1. Actors

| Actor | Goal |
|---|---|
| Human investigator | Upload an image; read verdict + per-signal evidence |
| API client | `POST /api/v1/analyze` (multipart image) |
| CI | ruff + pytest |
| Operator | Docker Compose / uvicorn serving API (+ built web UI) |

## 2. API (`/api/v1`)

Implemented in `apps/api/src/ai_image_authenticator/interfaces/http/v1/routes.py`.

| Method | Path | Role |
|---|---|---|
| GET | `/api/v1/health` | Liveness |
| GET | `/api/v1/ready` | Readiness + registered analyzer IDs (**12**) |
| POST | `/api/v1/analyze` | Analyze upload → verdict, probabilities, signals, evidence paths |
| GET | `/api/v1/artifacts/{id}` | Short-TTL visualization bytes |

Routes depend on `AnalysisService` via DI — no fusion math in HTTP handlers.

## 3. Clean Architecture layers

```
interfaces/http/          FastAPI adapters (routes, schemas, uploads, middleware)
application/analyzers/    Twelve Analyzer implementations + registry
application/services/     AnalysisService, WeightedFusionPolicy, weights SSOT
domain/                   models, ports, verdict
infrastructure/           image loader, OCR adapter, in-memory artifact store
container.py              DI composition root
main.py                   create_app(); mounts /api/v1 (+ SPA when dist exists)
```

Dependency rule: **inward only**. `AnalysisService` depends on ports
(`Analyzer`, `FusionPolicy`, `ArtifactStore`), not FastAPI/pytesseract.

## 4. Twelve analyzers

Registered in `container.build_registry()` (Open/Closed):

| id | Module | Role |
|---|---|---|
| metadata | `analyzers/metadata.py` | EXIF / software fingerprints |
| provenance | `analyzers/provenance.py` | C2PA / Content Credentials |
| labels | `analyzers/labels.py` | OCR Made-with-AI badges |
| ela | `analyzers/ela.py` | Error level / recompression residual |
| fft | `analyzers/fft.py` | Durall-style azimuthal spectrum |
| dct | `analyzers/dct.py` | JPEG / DCT / Benford-style stats |
| noise | `analyzers/noise.py` | Residual noise field |
| srm | `analyzers/srm.py` | SRM-style high-pass residual bank |
| bayar | `analyzers/bayar.py` | Constrained 3×3 prediction residual |
| local_corr | `analyzers/local_corr.py` | Local correlation / upsampling residue |
| texture | `analyzers/texture.py` | Gradient / GLCM texture |
| screenshot | `analyzers/screenshot.py` | UI chrome heuristic → content-crop reanalysis |

Protocol: `domain/ports.py` (`Analyzer`). Shared base: `analyzers/base.py`.

## 5. Fusion contract

- **Weights SSOT:** `application/services/weights.py` (`DEFAULT_WEIGHTS`, `WEIGHTS_VERSION="1.3"`)
- **Policy:** `WeightedFusionPolicy` in `application/services/fusion.py` (re-exports weights)
- Confidence-normalize scores before weighted sum
- Absent C2PA → near-zero provenance weight (non-dilution)
- OCR / generative C2PA hard floors ≥ 0.82 (C2PA only from claims inside a manifest container; a manifest the c2pa reader rejects never floors)
- Forensic agreement boost/dampen on expanded pixel set (includes srm/bayar/local_corr)
- Evidence paths: `provenance_contract` · `pixel_forensic` · `screenshot_path`
- Challenge awareness (v1.4): `challenge_flags`, `failure_modes`; JPEG Q=75/85 `laundering_probe` in AnalysisService
- Verdict bands: `real` / `inconclusive` / `likely_ai` / `ai_generated` (`domain/verdict.py`)

See `docs/weights.md`.

## 6. Screenshot path

1. `screenshot` analyzer estimates UI-chrome likelihood (requires chrome/layout cues —
   flat synthetic art alone is not enough).
2. If `is_screenshot`, `AnalysisService` crops central content and re-runs
   `build_content_analyzers()`.
3. Higher crop scores merge into base signals with `[content region]` findings.
4. Fusion records `screenshot_path` and dampens “camera photo” interpretations.
5. Together with OCR floors + absent-C2PA non-dilution, this is the **solved share path** when signed manifests are stripped.

## 7. OCR / C2PA paths

- **C2PA:** PNG `caBX` / JPEG APP11–JUMBF / WebP `C2PA` chunk; `digitalSourceType` read from manifest
  bytes only, classified per the C2PA conformance rubric (generative / possibly generative). With the
  optional `c2pa-python` reader: signature + hard-binding validation, remote manifest fetch disabled,
  no trust list configured (so `Valid`, never `Trusted`).
- **OCR:** pytesseract behind `OcrEngine` port. Disclosure phrasing counts anywhere; distinctive
  generator names count in badge-region crops or in phrasing; ordinary words (runway, gemini, …) only
  in phrasing. Empty OCR does not dilute fusion.
- **Decode:** 50 MP cap checked before decoding, 32 px minimum, 16-bit scaled, alpha composited over
  white, EXIF orientation applied, animated inputs analyzed on the first frame with a failure-mode note.

## 8. Web UI

`apps/web` — Vite + React feature layout. Dev proxy → API. Production: build
`dist/`; API serves SPA when present. `VerdictPanel` renders `challenge_flags` chips and
`failure_modes` list from the analyze response.

## 9. Docker / CI

- Root `Dockerfile` (multi-stage: API + web + Tesseract)
- `docker-compose.yml`
- GitHub Actions: ruff + pytest (with the `c2pa` extra, so real-signature tests run) + web build
- **No default GPU CLIP download in CI**

## 10. Honesty limits

Documented in fusion `LIMITATIONS`, README, and [research-challenges.md](./research-challenges.md):
no SynthID decode; no X-gate equivalence; no public leaderboard claims; classical
approximations; generator shift / bias remain open.
