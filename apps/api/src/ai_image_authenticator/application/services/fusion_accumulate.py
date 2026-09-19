"""Weighted signal accumulation for fusion (laundering-aware weights)."""

from __future__ import annotations

from ai_image_authenticator.application.services.challenge_flags import (
    LAUNDERING_SENSITIVE_IDS,
    estimate_compression_laundering,
    spectral_weight_scale,
)
from ai_image_authenticator.application.services.fusion_core import _normalize_score
from ai_image_authenticator.domain.models import AnalyzerOutput, SignalScore


def accumulate_weighted_signals(
    *,
    by_id: dict[str, AnalyzerOutput],
    weights: dict[str, float],
    visible_ai_label: bool,
    provenance_ai: bool,
    provenance_present: bool,
    viz_urls: dict[str, str | None],
) -> tuple[float, float, list[SignalScore], float]:
    """Return (ai_probability, confidence, signals, spectral_scale)."""
    laundering_score, _laun_notes = estimate_compression_laundering(by_id)
    spectral_scale = spectral_weight_scale(laundering_score)

    numer = 0.0
    denom = 0.0
    conf_numer = 0.0
    signals: list[SignalScore] = []

    for analyzer_id, weight in weights.items():
        out = by_id.get(analyzer_id)
        if out is None:
            continue
        effective_weight = weight
        if analyzer_id == "labels" and not visible_ai_label and out.score < 0.5:
            effective_weight = 0.03
        if analyzer_id == "provenance" and not provenance_ai and not provenance_present:
            effective_weight = 0.01  # absent C2PA ~ zero weight (non-dilution)
        elif analyzer_id == "provenance" and provenance_present and not provenance_ai:
            effective_weight = 0.035
        elif analyzer_id == "provenance" and provenance_ai:
            effective_weight = max(weight, 0.14)

        if analyzer_id in LAUNDERING_SENSITIVE_IDS and spectral_scale < 1.0:
            effective_weight = effective_weight * spectral_scale

        norm_score = _normalize_score(out.score, out.confidence)
        numer += norm_score * effective_weight
        denom += effective_weight
        conf_numer += out.confidence * effective_weight
        signals.append(
            SignalScore(
                id=out.id,
                name=out.name,
                score=round(out.score, 4),
                confidence=round(out.confidence, 4),
                weight=effective_weight,
                findings=out.findings,
                viz_url=viz_urls.get(out.id),
                details={
                    **(out.details or {}),
                    "normalized_score": round(norm_score, 4),
                },
            )
        )

    ai_probability = numer / denom if denom else 0.5
    confidence = conf_numer / denom if denom else 0.5
    return ai_probability, confidence, signals, spectral_scale
