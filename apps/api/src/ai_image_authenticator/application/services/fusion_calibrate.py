"""Post-sum challenge calibration for WeightedFusionPolicy."""

from __future__ import annotations

from ai_image_authenticator.application.services.challenge_flags import (
    CONFIDENCE_FLOOR,
    assess_challenges,
)
from ai_image_authenticator.application.services.fusion_core import PIXEL_FORENSIC_IDS
from ai_image_authenticator.domain.models import AnalyzerOutput


def apply_challenge_calibration(
    *,
    by_id: dict[str, AnalyzerOutput],
    outputs: list[AnalyzerOutput],
    ai_probability: float,
    confidence: float,
    provenance_ai: bool,
    visible_ai_label: bool,
) -> tuple[float, float, list[str], list[str], list[str]]:
    """Return (ai_probability, confidence, challenge_flags, extra_reasons, failure_modes)."""
    forensic_outs = [o for o in outputs if o.id in PIXEL_FORENSIC_IDS]
    forensic_scores = [o.score for o in forensic_outs]
    mean_forensic = (
        sum(forensic_scores) / len(forensic_scores) if forensic_scores else None
    )
    lean_ai = sum(1 for s in forensic_scores if s >= 0.58)
    lean_real = sum(1 for s in forensic_scores if s <= 0.35)
    assessment = assess_challenges(
        by_id,
        provenance_ai=provenance_ai,
        visible_ai_label=visible_ai_label,
        mean_forensic=mean_forensic,
        lean_ai=lean_ai,
        lean_real=lean_real,
        forensic_count=len(forensic_scores),
    )
    challenge_flags = list(assessment.flags)
    extra = list(assessment.reasons)
    failure_modes = list(assessment.failure_modes)
    confidence = float(max(CONFIDENCE_FLOOR, min(1.0, confidence * assessment.confidence_scale)))
    if assessment.inconclusive_pull > 0 and not provenance_ai and not visible_ai_label:
        pull = assessment.inconclusive_pull
        ai_probability = ai_probability + (0.5 - ai_probability) * pull
        extra.append(
            f"challenge: soft pull toward inconclusive (pull={pull:.2f}) after signal conflict"
        )
    elif assessment.inconclusive_pull > 0 and (provenance_ai or visible_ai_label):
        extra.append(
            "challenge: signal conflict noted; provenance hard-floor preserved "
            "(confidence reduced, probability floor kept)"
        )
    if challenge_flags:
        extra.append(
            "challenge: overconfidence controls — confidence floor "
            f"{CONFIDENCE_FLOOR:.2f} + challenge_flags={challenge_flags}"
        )
    return ai_probability, confidence, challenge_flags, extra, failure_modes
