"""Calibrated verdict bands (value object + mapping)."""

from __future__ import annotations

from enum import Enum

THRESHOLD_REAL = 0.35
THRESHOLD_INCONCLUSIVE = 0.55
THRESHOLD_LIKELY_AI = 0.75


class Verdict(str, Enum):
    REAL = "real"
    INCONCLUSIVE = "inconclusive"
    LIKELY_AI = "likely_ai"
    AI_GENERATED = "ai_generated"


def verdict_from_probability(prob: float) -> Verdict:
    if prob < THRESHOLD_REAL:
        return Verdict.REAL
    if prob < THRESHOLD_INCONCLUSIVE:
        return Verdict.INCONCLUSIVE
    if prob < THRESHOLD_LIKELY_AI:
        return Verdict.LIKELY_AI
    return Verdict.AI_GENERATED
