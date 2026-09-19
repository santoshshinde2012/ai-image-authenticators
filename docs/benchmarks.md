# Local benchmarks (measured only)

> **Not a public leaderboard.** Numbers below were measured by
> `scripts/run_local_benchmark.py` on images shipped in (or beside) this repo.
> We do **not** claim GenImage, NTIRE, or other public challenge scores.

## Methodology

- Harness: `scripts/run_local_benchmark.py` → `AnalysisService.analyze_bytes`
- Git SHA: `dcfa889514b901e980b33c100ad18f7fc297b614`
- Weights version: `1.3` (see `docs/weights.md` / `application/services/weights.py`)
- Analyzer count: **12** (`metadata, provenance, labels, ela, fft, dct, noise, srm, bayar, local_corr, texture, screenshot`)
- Ran at (UTC): `2026-09-18T07:05:50.151490+00:00`
- Machine note: agent box local run (Mac path used when reachable)

## Summary table

| Sample | Verdict | AI probability | Confidence | analysis_ms | Evidence paths | Analyzers | Screenshot |
|---|---|---:|---:|---:|---|---:|:---:|
| `samples/synthetic-screenshot.png` | `ai_generated` | 0.8889 | 0.6946 | 1251 | pixel_forensic, screenshot_path | 12 | yes |
| `samples/synthetic-smooth.png` | `ai_generated` | 0.8467 | 0.7649 | 946 | pixel_forensic | 12 | no |
| `ai-image-authenticator-samples/low-code-illusion-sample.png` | `ai_generated` | 0.9200 | 0.9000 | 4121 | provenance_contract | 12 | no |

## Per-sample key signal scores

### `samples/synthetic-screenshot.png`

| Signal | Score | Confidence | Effective weight |
|---|---:|---:|---:|
| `metadata` | 0.5800 | 0.5500 | 0.0500 |
| `provenance` | 0.4500 | 0.4000 | 0.0100 |
| `labels` | 0.4200 | 0.4500 | 0.0300 |
| `ela` | 0.7100 | 0.6800 | 0.0900 |
| `fft` | 0.7100 | 0.6000 | 0.1000 |
| `dct` | 0.8000 | 0.6700 | 0.0700 |
| `noise` | 0.7300 | 0.6300 | 0.0700 |
| `srm` | 0.9200 | 0.7900 | 0.1100 |
| `bayar` | 0.8600 | 0.7800 | 0.0700 |
| `local_corr` | 0.8200 | 0.7000 | 0.0900 |
| `texture` | 1.0000 | 0.7600 | 0.0700 |
| `screenshot` | 0.5200 | 0.7500 | 0.0400 |

Fusion notes:
- provenance_contract: no C2PA markers (typical after re-encode/screenshot) — not decisive
- pixel_forensic: classical ensemble mean=0.79 (lean_ai=9/9; ELA/FFT/DCT/noise/texture/metadata/SRM/Bayar/local_corr)
- pixel_forensic: agreement boost (+0.08) from 9 AI-leaning signals
- screenshot_path: UI chrome heuristic active; content-region reanalysis may apply
- challenge: laundering_probe — controlled JPEG Q=75 pass (Δ=-0.032); surfaced in fusion_reasons for audit
- challenge: overconfidence controls — confidence floor 0.12 + challenge_flags=['laundering_probe']

### `samples/synthetic-smooth.png`

| Signal | Score | Confidence | Effective weight |
|---|---:|---:|---:|
| `metadata` | 0.8500 | 0.9000 | 0.0500 |
| `provenance` | 0.4500 | 0.4000 | 0.0100 |
| `labels` | 0.4200 | 0.4500 | 0.0300 |
| `ela` | 0.8600 | 0.7400 | 0.0900 |
| `fft` | 0.9200 | 0.7200 | 0.1000 |
| `dct` | 0.5200 | 0.6700 | 0.0700 |
| `noise` | 0.8400 | 0.7200 | 0.0700 |
| `srm` | 0.9800 | 0.7900 | 0.1100 |
| `bayar` | 0.8500 | 0.7200 | 0.0700 |
| `local_corr` | 0.8200 | 0.7000 | 0.0900 |
| `texture` | 1.0000 | 0.7600 | 0.0700 |
| `screenshot` | 0.4500 | 0.5000 | 0.0400 |

Fusion notes:
- provenance_contract: no C2PA markers (typical after re-encode/screenshot) — not decisive
- pixel_forensic: classical ensemble mean=0.85 (lean_ai=8/9; ELA/FFT/DCT/noise/texture/metadata/SRM/Bayar/local_corr)
- pixel_forensic: agreement boost (+0.08) from 8 AI-leaning signals
- challenge: laundering_probe — controlled JPEG Q=75 pass (Δ=+0.013); surfaced in fusion_reasons for audit
- challenge: overconfidence controls — confidence floor 0.12 + challenge_flags=['laundering_probe']

### `ai-image-authenticator-samples/low-code-illusion-sample.png`

| Signal | Score | Confidence | Effective weight |
|---|---:|---:|---:|
| `metadata` | 0.4000 | 0.5000 | 0.0500 |
| `provenance` | 0.4500 | 0.4000 | 0.0100 |
| `labels` | 0.8915 | 0.9700 | 0.1400 |
| `ela` | 0.5200 | 0.6100 | 0.0900 |
| `fft` | 0.3000 | 0.5500 | 0.1000 |
| `dct` | 0.5200 | 0.6700 | 0.0700 |
| `noise` | 0.3000 | 0.5500 | 0.0700 |
| `srm` | 0.3300 | 0.6300 | 0.1100 |
| `bayar` | 0.6500 | 0.5500 | 0.0700 |
| `local_corr` | 0.4000 | 0.5500 | 0.0900 |
| `texture` | 0.4200 | 0.6100 | 0.0700 |
| `screenshot` | 0.4500 | 0.5000 | 0.0400 |

Fusion notes:
- provenance_contract: no C2PA markers (typical after re-encode/screenshot) — not decisive
- provenance_contract: visible Made-with-AI / generator disclosure via OCR (pixel badge)
- pixel_forensic: classical ensemble mean=0.43 (lean_ai=1/9; ELA/FFT/DCT/noise/texture/metadata/SRM/Bayar/local_corr)
- challenge: laundering_probe — controlled JPEG Q=75 pass (Δ=+0.000); surfaced in fusion_reasons for audit
- challenge: overconfidence controls — confidence floor 0.12 + challenge_flags=['laundering_probe']

## What we do **not** claim

- No GenImage / FakeAVCeleb / WildRF / NTIRE public leaderboard accuracy.
- No production traffic analytics or unpublished platform detector metrics.
- No SynthID decode rate (we do not verify proprietary watermarks).
- These local fixtures are **smoke/regression** assets, not a balanced eval set.

## How to run larger evals

```bash
# Local samples (writes samples/benchmarks/local_benchmark.json + docs/benchmarks.md)
uv run python scripts/run_local_benchmark.py

# Point the harness at your own folder by editing DEFAULT_SAMPLES or invoking AnalysisService
# against a directory of labeled images, then compute precision/recall yourself.
# For GenImage / NTIRE: download those datasets under a local data/ tree (not committed),
# iterate files, and record CSV — do not paste unverified leaderboard numbers into docs.
```

Raw JSON: `samples/benchmarks/local_benchmark.json`

