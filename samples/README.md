# Samples

Illustrative analysis JSON snapshots for docs/demos.

- Paths use `/api/v1/artifacts/...`
- Signal `id`s include all twelve analyzers (`metadata`, `provenance`, `labels`, `ela`, `fft`, `dct`, `noise`, `srm`, `bayar`, `local_corr`, `texture`, `screenshot`)
- Artifact ids are scrubbed to `/api/v1/artifacts/<id>` (real ids are random and expire after an hour)
- `evidence_paths` use `provenance_contract` | `pixel_forensic` | `screenshot_path`

Regenerate after fusion/analyzer changes by running analyze against `synthetic-smooth.png` (`sample-result.json`) and the low-code sample (`low-code-illusion-result.json`) and writing the scrubbed `AnalysisResult` JSON under this directory. `benchmarks/local_benchmark.json` is written by `scripts/run_local_benchmark.py`.
