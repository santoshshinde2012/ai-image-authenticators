"""Analysis orchestration — depends on ports, not concrete adapters."""

from __future__ import annotations

import time
from collections.abc import Sequence

import numpy as np
from PIL import Image

from ai_image_authenticator.application.services.probes import build_probe_output
from ai_image_authenticator.domain.models import AnalysisOutcome, AnalyzerOutput, LoadedImage
from ai_image_authenticator.domain.ports import Analyzer, ArtifactStore, FusionPolicy
from ai_image_authenticator.infrastructure.image_loader import load_image_bytes


def content_crop(rgb: np.ndarray) -> np.ndarray:
    """Crop away likely UI chrome: keep central ~70% body."""
    h, w = rgb.shape[:2]
    y0, y1 = int(h * 0.12), int(h * 0.92)
    x0, x1 = int(w * 0.08), int(w * 0.92)
    if y1 - y0 < 64 or x1 - x0 < 64:
        return rgb
    return rgb[y0:y1, x0:x1]


class AnalysisService:
    """Runs analyzers, stores viz artifacts, optionally reanalyzes content crops, then fuses.

    Also runs a controlled JPEG laundering/shift probe (``_probes``) so fusion can
    surface ``laundering_probe`` / ``generator_shift_uncertainty`` without inventing
    a SynthID decoder or a second GPU stack.
    """

    def __init__(
        self,
        analyzers: Sequence[Analyzer],
        fusion: FusionPolicy,
        artifacts: ArtifactStore,
        content_analyzers: Sequence[Analyzer] | None = None,
        probe_analyzers: Sequence[Analyzer] | None = None,
        enable_probes: bool = True,
        max_image_pixels: int | None = None,
    ) -> None:
        self._analyzers = list(analyzers)
        self._fusion = fusion
        self._artifacts = artifacts
        self._content_analyzers = list(content_analyzers or [])
        # Default probe bank = content analyzers (forensic subset) when not injected
        self._probe_analyzers = list(probe_analyzers or self._content_analyzers)
        self._enable_probes = enable_probes
        self._max_image_pixels = max_image_pixels

    def analyze_bytes(self, data: bytes, filename: str = "upload.png") -> AnalysisOutcome:
        loaded = load_image_bytes(data, filename, max_pixels=self._max_image_pixels)
        return self.analyze_loaded(loaded)

    def analyze_loaded(self, loaded: LoadedImage) -> AnalysisOutcome:
        started = time.perf_counter()
        outputs: list[AnalyzerOutput] = []
        viz_urls: dict[str, str | None] = {}

        for analyzer in self._analyzers:
            out = analyzer.analyze(loaded.image, loaded.rgb, loaded.raw_bytes, loaded.filename)
            outputs.append(out)
            if out.visualization:
                aid = self._artifacts.put(out.visualization, "image/png", f"{out.id}.png")
                viz_urls[out.id] = f"/api/v1/artifacts/{aid}"
            else:
                viz_urls[out.id] = None

        by_id = {o.id: o for o in outputs}
        shot = by_id.get("screenshot")
        if shot and shot.details.get("is_screenshot") and self._content_analyzers:
            crop = content_crop(loaded.rgb)
            crop_img = Image.fromarray(crop)
            for analyzer in self._content_analyzers:
                crop_out = analyzer.analyze(crop_img, crop, loaded.raw_bytes, loaded.filename)
                base = by_id.get(analyzer.id)
                if base is None:
                    continue
                if crop_out.score > base.score:
                    merged_findings = list(base.findings)
                    for f in crop_out.findings:
                        tagged = f"[content region] {f}"
                        if tagged not in merged_findings:
                            merged_findings.append(tagged)
                    base.score = float(max(base.score, crop_out.score))
                    base.confidence = float(max(base.confidence, crop_out.confidence * 0.95))
                    base.findings = merged_findings
                    base.details = {
                        **base.details,
                        "content_region_score": crop_out.score,
                        "content_region_details": crop_out.details,
                    }
                    if crop_out.visualization and not base.visualization:
                        base.visualization = crop_out.visualization
                        aid = self._artifacts.put(
                            crop_out.visualization, "image/png", f"{base.id}-crop.png"
                        )
                        viz_urls[base.id] = f"/api/v1/artifacts/{aid}"

        # Controlled JPEG degradation probe (laundering + mild generator-shift uncertainty)
        if self._enable_probes and self._probe_analyzers:
            try:
                probe_out = build_probe_output(
                    clean_by_id=by_id,
                    probe_analyzers=self._probe_analyzers,
                    rgb=loaded.rgb,
                    filename=loaded.filename,
                )
                outputs.append(probe_out)
                viz_urls[probe_out.id] = None
            except Exception as exc:  # noqa: BLE001 — probes must never fail the analyze path
                outputs.append(
                    AnalyzerOutput(
                        id="_probes",
                        name="Degradation probes",
                        score=0.5,
                        confidence=0.2,
                        findings=[f"Probe skipped: {type(exc).__name__}"],
                        details={"laundering_probe": False, "error": str(exc)[:200]},
                    )
                )

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        outcome = self._fusion.fuse(
            outputs,
            viz_urls,
            loaded.filename,
            [loaded.width, loaded.height],
            elapsed_ms,
        )
        # Decoding choices (first frame only, alpha flattened, …) are ways the answer can be wrong
        for note in loaded.decode_notes:
            outcome.failure_modes.append(f"Input: {note}.")
        return outcome
