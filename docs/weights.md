# Research-grade fusion weights (v1.3)

Sum = **1.0**. **Single source of truth in code:**
`apps/api/src/ai_image_authenticator/application/services/weights.py`
(`DEFAULT_WEIGHTS`, `WEIGHTS_VERSION = "1.3"`).

`fusion.py` re-exports `DEFAULT_WEIGHTS` / `WEIGHTS` for back-compat — do not edit
weights in `fusion.py`.

| id | weight | research note |
|---|---:|---|
| metadata | 0.05 | EXIF / software fingerprints |
| provenance | 0.10 | C2PA; ~0.01 when absent (non-dilution) |
| labels | 0.14 | OCR Made-with-AI disclosures |
| ela | 0.09 | Error level analysis |
| fft | 0.10 | Durall CVPR 2020 azimuthal / log-log spectrum |
| dct | 0.07 | JPEG / Benford stats |
| noise | 0.07 | Residual noise field |
| srm | 0.11 | Fridrich & Kodovský SRM / TRIDENT residual bank |
| bayar | 0.07 | Bayar constrained prediction residual |
| local_corr | 0.09 | NPR / ForenAgent local correlation + upsampling residue |
| texture | 0.07 | Gradient / GLCM |
| screenshot | 0.04 | UI chrome heuristic |

## Fusion extras
- Challenge-aware fusion policy (on weights v1.3): `challenge_flags` + `failure_modes`; JPEG probes; spectral dampen under laundering
- Confidence-normalize analyzer scores before weighted sum
- Forensic agreement boost/dampen on expanded pixel set (includes srm/bayar/local_corr)
- OCR / C2PA hard floors ≥ 0.82 when generative disclosure present
- Evidence paths: `provenance_contract`, `pixel_forensic`, `screenshot_path`

## Analyzer IDs (12)
`metadata`, `provenance`, `labels`, `ela`, `fft`, `dct`, `noise`, `srm`, `bayar`, `local_corr`, `texture`, `screenshot`
