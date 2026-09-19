"""Weighted ensemble fusion — FusionPolicy implementation (Single Responsibility).

Challenge-aware fusion (challenge_flags + failure_modes) on weights v1.3. Helpers in fusion_core.py;
policy class in fusion_policy.py; challenge heuristics in challenge_flags.py.
"""

from __future__ import annotations

from ai_image_authenticator.application.services.fusion_core import (
    DEFAULT_WEIGHTS,
    WEIGHTS,
    _normalize_score,
    fusion_math,
)
from ai_image_authenticator.application.services.fusion_policy import WeightedFusionPolicy
from ai_image_authenticator.domain.verdict import verdict_from_probability

__all__ = [
    "DEFAULT_WEIGHTS",
    "WEIGHTS",
    "WeightedFusionPolicy",
    "fusion_math",
    "_normalize_score",
]


def _verdict(prob: float) -> str:
    return verdict_from_probability(prob).value
