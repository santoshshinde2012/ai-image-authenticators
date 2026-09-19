"""Controlled degradation probes (TRIDENT-style curriculum lite).

Runs one or two JPEG re-encodes and measures forensic lean drift vs the clean
pass. Used for compression-laundering awareness and generator-shift uncertainty —
not a second full analysis pipeline.
"""

from __future__ import annotations

import io
from typing import Any

import numpy as np
from PIL import Image

from ai_image_authenticator.domain.models import AnalyzerOutput
from ai_image_authenticator.domain.ports import Analyzer

# Compact forensic subset for probe (CPU-cheap; IDs stable). The clean and degraded
# means are always computed over the ids that actually ran, so they stay comparable.
PROBE_ANALYZER_IDS = frozenset({"ela", "fft", "srm", "bayar", "local_corr", "noise"})


def jpeg_reencode(rgb: np.ndarray, quality: int) -> tuple[Image.Image, np.ndarray, bytes]:
    """Re-encode RGB array as JPEG at ``quality`` and reload."""
    q = int(max(1, min(95, quality)))
    img = Image.fromarray(np.asarray(rgb, dtype=np.uint8), mode="RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=q, optimize=False)
    raw = buf.getvalue()
    out = Image.open(io.BytesIO(raw)).convert("RGB")
    # convert() drops .format; analyzers that key on it must see the re-encode as a JPEG
    out.format = "JPEG"
    arr = np.asarray(out, dtype=np.uint8)
    return out, arr, raw


def forensic_lean(
    outputs: list[AnalyzerOutput], ids: frozenset[str] = PROBE_ANALYZER_IDS
) -> dict[str, Any]:
    """Mean score + AI/real lean counts over ``ids``."""
    scores = [o.score for o in outputs if o.id in ids]
    if not scores:
        return {"mean": None, "lean_ai": 0, "lean_real": 0, "count": 0, "scores": {}}
    lean_ai = sum(1 for s in scores if s >= 0.58)
    lean_real = sum(1 for s in scores if s <= 0.35)
    return {
        "mean": float(sum(scores) / len(scores)),
        "lean_ai": lean_ai,
        "lean_real": lean_real,
        "count": len(scores),
        "scores": {o.id: round(o.score, 4) for o in outputs if o.id in ids},
    }


def run_jpeg_probe(
    analyzers: list[Analyzer],
    rgb: np.ndarray,
    filename: str,
    quality: int,
    ids: frozenset[str] = PROBE_ANALYZER_IDS,
) -> dict[str, Any]:
    """Run subset analyzers on a JPEG re-encode; return lean summary."""
    img, arr, raw = jpeg_reencode(rgb, quality)
    outs: list[AnalyzerOutput] = []
    for analyzer in analyzers:
        if analyzer.id not in ids:
            continue
        outs.append(analyzer.analyze(img, arr, raw, filename))
    lean = forensic_lean(outs, ids)
    lean["quality"] = int(quality)
    return lean


def build_probe_output(
    *,
    clean_by_id: dict[str, AnalyzerOutput],
    probe_analyzers: list[Analyzer],
    rgb: np.ndarray,
    filename: str,
) -> AnalyzerOutput:
    """Execute Q=75 laundering probe + Q=85 mild shift probe; pack into one output.

    The output id ``_probes`` is intentionally absent from fusion weights so it
    never dilutes the ensemble; challenge_flags reads ``details`` only.
    """
    # Compare like with like: only ids that the probe bank can actually re-run
    ran = frozenset(a.id for a in probe_analyzers) & PROBE_ANALYZER_IDS
    clean_lean = forensic_lean(list(clean_by_id.values()), ran)
    q75 = run_jpeg_probe(probe_analyzers, rgb, filename, 75, ran)
    q85 = run_jpeg_probe(probe_analyzers, rgb, filename, 85, ran)

    clean_mean = clean_lean.get("mean")
    q75_mean = q75.get("mean")
    q85_mean = q85.get("mean")

    delta_75 = None
    delta_85 = None
    if clean_mean is not None and q75_mean is not None:
        delta_75 = float(q75_mean - clean_mean)
    if clean_mean is not None and q85_mean is not None:
        delta_85 = float(q85_mean - clean_mean)

    # Disagreement: probe flips lean direction or moves mean by >= 0.12
    disagree_75 = False
    if clean_mean is not None and q75_mean is not None:
        clean_ai = clean_mean >= 0.58
        clean_real = clean_mean <= 0.35
        probe_ai = q75_mean >= 0.58
        probe_real = q75_mean <= 0.35
        if abs(delta_75 or 0.0) >= 0.12:
            disagree_75 = True
        if (clean_ai and probe_real) or (clean_real and probe_ai):
            disagree_75 = True

    disagree_85 = False
    if clean_mean is not None and q85_mean is not None:
        clean_ai = clean_mean >= 0.58
        clean_real = clean_mean <= 0.35
        probe_ai = q85_mean >= 0.58
        probe_real = q85_mean <= 0.35
        if abs(delta_85 or 0.0) >= 0.10:
            disagree_85 = True
        if (clean_ai and probe_real) or (clean_real and probe_ai):
            disagree_85 = True

    findings = [
        "Controlled JPEG degradation probe (Q=75 laundering + Q=85 mild shift)",
    ]
    if delta_75 is not None:
        findings.append(f"Q=75 forensic mean delta vs clean: {delta_75:+.3f}")
    if delta_85 is not None:
        findings.append(f"Q=85 forensic mean delta vs clean: {delta_85:+.3f}")

    details: dict[str, Any] = {
        "laundering_probe": True,
        "probe_ids": sorted(ran),
        "clean": clean_lean,
        "jpeg_q75": q75,
        "jpeg_q85": q85,
        "delta_q75": delta_75,
        "delta_q85": delta_85,
        "probe_disagrees_q75": disagree_75,
        "probe_disagrees_q85": disagree_85,
        "generator_shift_uncertainty": bool(disagree_85 or disagree_75),
    }

    return AnalyzerOutput(
        id="_probes",
        name="Degradation probes",
        score=0.5,
        confidence=0.5,
        findings=findings,
        details=details,
    )
