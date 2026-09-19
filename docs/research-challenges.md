# Research challenges → concrete solutions

Common goals for an AI-image authenticity examiner:

1. **Detect** synthetic / AI imagery (full-frame generative and heavily synthetic edits).
2. **Survive real-world abuse** — re-encode, resize, blur, screenshots, unseen generators.
3. **Auditable decisions** — per-signal scores, `fusion_reasons`, `evidence_paths`, `challenge_flags`, `failure_modes`, visualizations.
4. **Combine provenance + pixels** — C2PA / OCR when present; classical forensics when stripped.

This table maps each challenge to the **Solution we ship** and a honest **Status**. Prefer **Mitigated** when a concrete mechanism exists; keep **Accepted** only for true impossibilities (proprietary watermark crypto without keys). Citations are limited to verified URLs in [references.md](./references.md) (no invented leaderboard numbers).

| Challenge | Solution (what we ship) | Status |
|---|---|---|
| **Generator / domain shift** | Heterogeneous twelve-analyzer fusion (HEDGE/TRIDENT *spirit*) + optional mild degradation probe (JPEG Q=75/85 forensic lean vs clean). Flag `generator_shift_uncertainty` when probe disagrees with clean pass; soft pull toward inconclusive. | **Mitigated** — [HEDGE 2604.03555](https://arxiv.org/abs/2604.03555), [survey 2502.19716](https://arxiv.org/abs/2502.19716), [OOD 2602.07814](https://arxiv.org/abs/2602.07814), [shift 2608.11643](https://arxiv.org/abs/2608.11643), [TRIDENT](https://openaccess.thecvf.com/content/CVPR2026W/NTIRE/html/Sharma_TRIDENT_Robust_Deepfake_Detection_via_Tri-Modal_Forensic_Ensembles_CVPRW_2026_paper.html) |
| **Compression / resize / blur laundering** | Heuristic `compression_laundering` from ELA/DCT/screenshot + explicit **`laundering_probe`** path in `AnalysisService` (two controlled JPEG passes, Q=75 and Q=85, compared over the same analyzer set as the clean pass). Spectral weights dampened; surfaced in `fusion_reasons`. | **Mitigated** |
| **Screenshot / C2PA strip** | Screenshot chrome heuristic + content-region reanalysis + OCR hard-floor for visible badges (disclosure phrasing, or distinctive generator names in badge regions; ordinary words never count alone) + absent-C2PA near-zero weight (non-dilution). **Solved for the share path** (pixels + OCR when the signed contract is gone). | **Mitigated** (share path) — [Bakshi](https://medium.com/agileinsider/i-investigated-how-x-detects-ai-generated-images-its-not-synthid-acb2a4bfab44), [C2PA 2.4](https://spec.c2pa.org/specifications/specifications/2.4/specs/C2PA_Specification.html) |
| **C2PA alone + SynthID dual-layer** | When C2PA mentions watermarked / soft-binding / unbound assertions → `dual_layer_provenance_hint` + `synthid_layer_not_verified`. **Never claim verified SynthID** (no provider keys). C2PA+OCR+pixels remain inspectable. | **Accepted** (SynthID decode) / **Mitigated** (dual-layer *awareness*) — [C2PA white paper](https://c2pa.org/wp-content/uploads/sites/33/2026/07/Use-of-Content-Credentials-to-Identify-Synthetic-and-Non-Synthetic-Content.pdf), [SynthID](https://deepmind.google/models/synthid/), [Roboin](https://roboin.io/article/en/2026/03/24/why-x-tags-posts-as-made-with-ai-and-how-to-remove-it-testing-the-conditions/) |
| **Single-signal overconfidence** | Weighted ensemble + confidence normalization + agreement boost/dampen + `challenge_flags` + **confidence floor** + response `failure_modes` (static + dynamic). | **Mitigated** — [2504.02898](https://arxiv.org/abs/2504.02898), [2609.11188](https://arxiv.org/abs/2609.11188) |
| **Transformation / dataset bias** | Document bias; flag `transform_bias_risk` when laundering high; prefer inconclusive under conflict; no public-leaderboard claims. | **Mitigated** (flag + calibration) / residual bias **Accepted** — [BIAS-ID 2605.31153](https://arxiv.org/abs/2605.31153) |
| **Frequency / SRM brittleness** | Durall FFT + compact SRM/Bayar as *witnesses*, not sole judges; dampen under laundering; flag `frequency_srm_brittleness`. | **Mitigated** — [Durall CVPR 2020](https://openaccess.thecvf.com/content_CVPR_2020/html/Durall_Watch_Your_Up-Convolution_CNN_Based_Generative_Deep_Neural_Networks_Are_CVPR_2020_paper.html), [Fridrich SRM](https://ieeexplore.ieee.org/document/6165621), [Bayar](https://ieeexplore.ieee.org/document/7544586) |
| **No universal detector** | Explicit `failure_modes` catalog on every analyze response (static honesty strings + dynamic from flags). Article section; Phase-2 ML optional/off; no CLIP/GPU default. | **Accepted** (impossibility) / **Mitigated** (calibrated disclosure) |

## Challenge flags (API)

`POST /api/v1/analyze` includes `challenge_flags: string[]` and `failure_modes: string[]`:

| Flag | Meaning |
|---|---|
| `compression_laundering` | Re-encode / screenshot laundering cues elevated; spectral/SRM weights dampened |
| `laundering_probe` | Controlled JPEG Q=75 and Q=85 probes ran (AnalysisService path) — an audit marker on every request, not a detection |
| `generator_shift_uncertainty` | Degradation probe disagrees with clean forensic lean |
| `dual_layer_provenance_hint` | C2PA soft-binding / watermarked assertion present |
| `synthid_layer_not_verified` | Watermark layer implied — **not** verified (no keys) |
| `transform_bias_risk` | High laundering → transformation/dataset-bias risk |
| `frequency_srm_brittleness` | Spectral path treated as witness; dampened |
| `signal_disagreement` | Provenance vs pixels and/or camera EXIF vs forensics disagree |
| `provenance_vs_pixels_conflict` | OCR/C2PA lean AI while classical pixels lean real |
| `possible_overprocessed_camera_photo` | Camera EXIF present with strong AI-leaning forensics |

Flags are **diagnostic**, not proof. See `WeightedFusionPolicy`, `challenge_flags.py`, `probes.py`.

## Notes on scope

- "Dual-layer" (C2PA metadata + an imperceptible watermark) is an EU-side expectation: the EU Code of
  Practice asks for both, while China's GB 45438-2025 mandates metadata and only *permits* watermarks.
- Only `digitalSourceType` claims inside a manifest container can set the provenance floor, and the
  generative set follows the C2PA conformance rubric (see [gap-analysis.md](./gap-analysis.md) P0-2).

## Accepted limits (do not overclaim)

- We do **not** decode SynthID or other proprietary watermarks — we surface *awareness* flags only.
- We do **not** claim X’s Made with AI gate equivalence ([Roboin](https://roboin.io/article/en/2026/03/24/why-x-tags-posts-as-made-with-ai-and-how-to-remove-it-testing-the-conditions/) nuance).
- We do **not** publish GenImage/NTIRE scores for this repository.
- Compact SRM/Bayar/local-corr are classical approximations, not full trained CNNs.
- Generator shift and transformation bias remain **open**; probes and flags reduce overconfidence — they do not eliminate error.
