"""WeightedFusionPolicy — challenge-aware ensemble fusion on weights v1.3."""

from __future__ import annotations

from ai_image_authenticator.application.services.fusion_accumulate import (
    accumulate_weighted_signals,
)
from ai_image_authenticator.application.services.fusion_calibrate import (
    apply_challenge_calibration,
)
from ai_image_authenticator.application.services.fusion_core import (
    DEFAULT_WEIGHTS,
    LIMITATIONS,
    PIXEL_FORENSIC_IDS,
    PROVENANCE_CONTRACT_IDS,
    _summary,
)
from ai_image_authenticator.domain.models import AnalysisOutcome, AnalyzerOutput
from ai_image_authenticator.domain.verdict import verdict_from_probability


class WeightedFusionPolicy:
    """Fuses analyzer outputs only — no image I/O, no HTTP, no storage."""

    def __init__(self, weights: dict[str, float] | None = None) -> None:
        self.weights = dict(weights or DEFAULT_WEIGHTS)

    def fuse(
        self,
        outputs: list[AnalyzerOutput],
        viz_urls: dict[str, str | None],
        filename: str,
        dimensions: list[int],
        analysis_ms: int,
    ) -> AnalysisOutcome:
        by_id = {o.id: o for o in outputs}
        screenshot_out = by_id.get("screenshot")
        screenshot_detected = bool(screenshot_out and screenshot_out.details.get("is_screenshot"))
        labels_out = by_id.get("labels")
        visible_ai_label = bool(labels_out and labels_out.details.get("ai_label_hits"))
        provenance_out = by_id.get("provenance")
        provenance_ai = bool(
            provenance_out and provenance_out.details.get("ai_digital_source_types")
        )
        provenance_present = bool(
            provenance_out and provenance_out.details.get("manifest_present")
        )

        ai_probability, confidence, signals, _spectral_scale = accumulate_weighted_signals(
            by_id=by_id,
            weights=self.weights,
            visible_ai_label=visible_ai_label,
            provenance_ai=provenance_ai,
            provenance_present=provenance_present,
            viz_urls=viz_urls,
        )

        reasons: list[str] = []
        evidence_paths: list[str] = []

        if provenance_ai:
            ai_probability = max(ai_probability, 0.82)
            confidence = max(confidence, 0.88)
            reasons.append(
                "provenance_contract: C2PA digitalSourceType generative assertion present"
            )
            if "provenance_contract" not in evidence_paths:
                evidence_paths.append("provenance_contract")
        elif provenance_present:
            reasons.append(
                "provenance_contract: C2PA markers present without extracted generative source type"
            )
            if "provenance_contract" not in evidence_paths:
                evidence_paths.append("provenance_contract")
        else:
            reasons.append(
                "provenance_contract: no C2PA markers (typical after re-encode/screenshot) — not decisive"
            )

        if visible_ai_label:
            hit_confs = (labels_out.details or {}).get("hit_confidences") or {}
            floor = 0.82
            if hit_confs:
                best = max(float(v) for v in hit_confs.values())
                floor = max(0.82, min(0.92, 0.75 + 0.2 * best))
            ai_probability = max(ai_probability, floor)
            confidence = max(confidence, 0.88 if floor <= 0.85 else 0.9)
            reasons.append(
                "provenance_contract: visible Made-with-AI / generator disclosure via OCR (pixel badge)"
            )
            if "provenance_contract" not in evidence_paths:
                evidence_paths.append("provenance_contract")

        forensic_outs = [o for o in outputs if o.id in PIXEL_FORENSIC_IDS]
        forensic_scores = [o.score for o in forensic_outs]
        if forensic_scores:
            mean_forensic = sum(forensic_scores) / len(forensic_scores)
            lean_ai = sum(1 for s in forensic_scores if s >= 0.58)
            lean_real = sum(1 for s in forensic_scores if s <= 0.35)
            reasons.append(
                f"pixel_forensic: classical ensemble mean={mean_forensic:.2f} "
                f"(lean_ai={lean_ai}/{len(forensic_scores)}; "
                "ELA/FFT/DCT/noise/texture/metadata/SRM/Bayar/local_corr)"
            )
            if mean_forensic >= 0.55 or (not provenance_ai and not visible_ai_label):
                if "pixel_forensic" not in evidence_paths:
                    evidence_paths.append("pixel_forensic")
            if lean_ai >= 3 and not provenance_ai and not visible_ai_label:
                boost = 0.04 + 0.02 * min(2, lean_ai - 3)
                ai_probability = min(0.95, ai_probability + boost)
                confidence = min(0.9, confidence + 0.05)
                reasons.append(
                    f"pixel_forensic: agreement boost (+{boost:.2f}) from {lean_ai} AI-leaning signals"
                )
            elif lean_real >= 4 and not provenance_ai and not visible_ai_label:
                ai_probability = max(0.05, ai_probability - 0.04)
                reasons.append(
                    f"pixel_forensic: agreement dampener from {lean_real} real-leaning signals"
                )

        if screenshot_detected:
            if "screenshot_path" not in evidence_paths:
                evidence_paths.append("screenshot_path")
            reasons.append(
                "screenshot_path: UI chrome heuristic active; content-region reanalysis may apply"
            )
            if ai_probability < 0.4 and not visible_ai_label and not provenance_ai:
                ai_probability = max(ai_probability, 0.38)
                confidence = min(confidence, 0.55)
            else:
                confidence = max(0.4, confidence * 0.95)

            other_scores = [
                o.score
                for o in outputs
                if o.id not in PROVENANCE_CONTRACT_IDS and o.id != "screenshot"
            ]
            if other_scores and (sum(other_scores) / len(other_scores)) >= 0.5:
                ai_probability = min(0.95, ai_probability + 0.05)

            noise = by_id.get("noise")
            if noise and float(noise.details.get("variance_cv", 0) or 0) > 1.8:
                ai_probability = min(0.95, ai_probability + 0.04)

        (
            ai_probability,
            confidence,
            challenge_flags,
            extra_reasons,
            failure_modes,
        ) = apply_challenge_calibration(
            by_id=by_id,
            outputs=outputs,
            ai_probability=ai_probability,
            confidence=confidence,
            provenance_ai=provenance_ai,
            visible_ai_label=visible_ai_label,
        )
        reasons.extend(extra_reasons)

        if not evidence_paths:
            evidence_paths.append("pixel_forensic")

        ai_probability = float(max(0.0, min(1.0, ai_probability)))
        confidence = float(max(0.0, min(1.0, confidence)))
        verdict = verdict_from_probability(ai_probability)

        ranked = sorted(
            outputs, key=lambda o: o.score * self.weights.get(o.id, 0.05), reverse=True
        )
        top_findings: list[str] = []
        for o in ranked:
            for f in o.findings:
                if f not in top_findings:
                    top_findings.append(f)
                if len(top_findings) >= 5:
                    break
            if len(top_findings) >= 5:
                break

        return AnalysisOutcome(
            verdict=verdict,
            ai_probability=round(ai_probability, 4),
            confidence=round(confidence, 4),
            summary=_summary(
                verdict, ai_probability, screenshot_detected, top_findings, evidence_paths
            ),
            signals=signals,
            limitations=list(LIMITATIONS),
            filename=filename,
            dimensions=dimensions,
            screenshot_detected=screenshot_detected,
            analysis_ms=analysis_ms,
            evidence_paths=evidence_paths,
            fusion_reasons=reasons,
            challenge_flags=challenge_flags,
            failure_modes=failure_modes,
        )
