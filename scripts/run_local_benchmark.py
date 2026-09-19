#!/usr/bin/env python3
"""Run local-only authenticity benchmarks on repo samples.

Records measured outcomes only. Does NOT claim GenImage/NTIRE/public leaderboard scores.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))

from ai_image_authenticator.application.services.weights import (  # noqa: E402
    DEFAULT_WEIGHTS,
    WEIGHTS_VERSION,
)
from ai_image_authenticator.container import create_container  # noqa: E402

DEFAULT_SAMPLES = [
    ROOT / "samples" / "synthetic-screenshot.png",
    ROOT / "samples" / "synthetic-smooth.png"
]

LOW_CODE_CANDIDATES = [
    ROOT / "samples" / "low-code-illusion-sample.png",
    ROOT.parent / "ai-image-authenticator-samples" / "low-code-illusion-sample.png",
]


def git_sha() -> str:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        )
    except Exception:  # noqa: BLE001
        return "unknown"


def outcome_to_dict(path: Path, outcome) -> dict:
    signals = []
    for s in outcome.signals:
        signals.append(
            {
                "id": s.id,
                "name": s.name,
                "score": round(float(s.score), 4),
                "confidence": round(float(s.confidence), 4),
                "weight": round(float(s.weight), 4),
                "findings": list(s.findings or [])[:5],
                "key_details": {
                    k: s.details.get(k)
                    for k in list(s.details or {})[:8]
                    if isinstance(s.details.get(k), (int, float, str, bool))
                },
            }
        )
    verdict = outcome.verdict.value if hasattr(outcome.verdict, "value") else str(outcome.verdict)
    return {
        "sample": (
            str(path.relative_to(ROOT))
            if path.is_relative_to(ROOT)
            else str(path.resolve().relative_to(ROOT.parent))
            if path.resolve().is_relative_to(ROOT.parent)
            else path.name
        ),
        "filename": path.name,
        "verdict": verdict,
        "ai_probability": round(float(outcome.ai_probability), 4),
        "confidence": round(float(outcome.confidence), 4),
        "analysis_ms": int(outcome.analysis_ms),
        "evidence_paths": list(outcome.evidence_paths or []),
        "screenshot_detected": bool(outcome.screenshot_detected),
        "analyzer_count": len(outcome.signals),
        "dimensions": list(outcome.dimensions or []),
        "signals": signals,
        "summary": outcome.summary,
        "fusion_reasons": list(getattr(outcome, "fusion_reasons", []) or [])[:12],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-json",
        type=Path,
        default=ROOT / "samples" / "benchmarks" / "local_benchmark.json",
    )
    parser.add_argument(
        "--out-md",
        type=Path,
        default=ROOT / "docs" / "benchmarks.md",
    )
    args = parser.parse_args()

    samples: list[Path] = [p for p in DEFAULT_SAMPLES if p.is_file()]
    low = next((p for p in LOW_CODE_CANDIDATES if p.is_file()), None)
    skipped_low_code = low is None
    if low is not None:
        samples.append(low)

    if not samples:
        print("No sample images found.", file=sys.stderr)
        return 1

    box = create_container()
    sha = git_sha()
    results = []
    for path in samples:
        data = path.read_bytes()
        outcome = box.analysis_service.analyze_bytes(data, path.name)
        results.append(outcome_to_dict(path, outcome))
        print(
            f"{path.name}: verdict={results[-1]['verdict']} "
            f"ai={results[-1]['ai_probability']:.4f} "
            f"conf={results[-1]['confidence']:.4f} "
            f"ms={results[-1]['analysis_ms']} "
            f"paths={results[-1]['evidence_paths']}"
        )

    payload = {
        "benchmark_type": "local_samples_only",
        "disclaimer": (
            "Measured on repository sample images only. "
            "Not a GenImage/NTIRE/public leaderboard result."
        ),
        "git_sha": sha,
        "weights_version": WEIGHTS_VERSION,
        "weights": dict(DEFAULT_WEIGHTS),
        "analyzer_ids": list(box.analyzer_ids),
        "analyzer_count": len(box.analyzer_ids),
        "ran_at_utc": datetime.now(UTC).isoformat(),
        "low_code_sample_found": not skipped_low_code,
        "results": results,
    }

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(payload, indent=2) + "\n")

    lines = [
        "# Local benchmarks (measured only)",
        "",
        "> **Not a public leaderboard.** Numbers below were measured by",
        "> `scripts/run_local_benchmark.py` on images shipped in (or beside) this repo.",
        "> We do **not** claim GenImage, NTIRE, or other public challenge scores.",
        "",
        "## Methodology",
        "",
        "- Harness: `scripts/run_local_benchmark.py` \u2192 `AnalysisService.analyze_bytes`",
        f"- Git SHA: `{sha}`",
        f"- Weights version: `{WEIGHTS_VERSION}` (see `docs/weights.md` / `application/services/weights.py`)",
        f"- Analyzer count: **{len(box.analyzer_ids)}** (`{', '.join(box.analyzer_ids)}`)",
        f"- Ran at (UTC): `{payload['ran_at_utc']}`",
        "- Machine note: agent box local run (Mac path used when reachable)",
        "",
        "## Summary table",
        "",
        "| Sample | Verdict | AI probability | Confidence | analysis_ms | Evidence paths | Analyzers | Screenshot |",
        "|---|---|---:|---:|---:|---|---:|:---:|",
    ]
    for r in results:
        lines.append(
            "| `{sample}` | `{verdict}` | {ai_probability:.4f} | {confidence:.4f} | {analysis_ms} | {paths} | {analyzer_count} | {shot} |".format(
                sample=r["sample"],
                verdict=r["verdict"],
                ai_probability=r["ai_probability"],
                confidence=r["confidence"],
                analysis_ms=r["analysis_ms"],
                paths=", ".join(r["evidence_paths"]) or "\u2014",
                analyzer_count=r["analyzer_count"],
                shot="yes" if r["screenshot_detected"] else "no",
            )
        )

    lines += [
        "",
        "## Per-sample key signal scores",
        "",
    ]
    for r in results:
        lines.append(f"### `{r['sample']}`")
        lines.append("")
        lines.append("| Signal | Score | Confidence | Effective weight |")
        lines.append("|---|---:|---:|---:|")
        for s in r["signals"]:
            lines.append(
                f"| `{s['id']}` | {s['score']:.4f} | {s['confidence']:.4f} | {s['weight']:.4f} |"
            )
        lines.append("")
        if r["fusion_reasons"]:
            lines.append("Fusion notes:")
            for reason in r["fusion_reasons"][:8]:
                lines.append(f"- {reason}")
            lines.append("")

    if skipped_low_code:
        lines += [
            "## Low-code sample",
            "",
            "Optional file "
            "`../ai-image-authenticator-samples/low-code-illusion-sample.png` (relative to repo) "
            "was **not found** on this runner. Prior committed JSON "
            "`samples/low-code-illusion-result.json` is historical and may predate the 12-analyzer bank \u2014 "
            "re-run the harness on Mac when that PNG is available.",
            "",
        ]

    lines += [
        "## What we do **not** claim",
        "",
        "- No GenImage / FakeAVCeleb / WildRF / NTIRE public leaderboard accuracy.",
        "- No production traffic analytics or unpublished platform detector metrics.",
        "- No SynthID decode rate (we do not verify proprietary watermarks).",
        "- These local fixtures are **smoke/regression** assets, not a balanced eval set.",
        "",
        "## How to run larger evals",
        "",
        "```bash",
        "# Local samples (writes samples/benchmarks/local_benchmark.json + docs/benchmarks.md)",
        "uv run python scripts/run_local_benchmark.py",
        "",
        "# Point the harness at your own folder by editing DEFAULT_SAMPLES or invoking AnalysisService",
        "# against a directory of labeled images, then compute precision/recall yourself.",
        "# For GenImage / NTIRE: download those datasets under a local data/ tree (not committed),",
        "# iterate files, and record CSV \u2014 do not paste unverified leaderboard numbers into docs.",
        "```",
        "",
        f"Raw JSON: `{args.out_json.relative_to(ROOT)}`",
        "",
    ]
    args.out_md.write_text("\n".join(lines) + "\n")
    print(f"Wrote {args.out_json}")
    print(f"Wrote {args.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
