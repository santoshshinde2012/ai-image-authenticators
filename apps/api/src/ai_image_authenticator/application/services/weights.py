"""Single source of truth for fusion weights (v1.3).

Keep ``docs/weights.md`` in lockstep with ``DEFAULT_WEIGHTS`` below.
Fusion and tests MUST import from this module — do not duplicate tables elsewhere.
"""

from __future__ import annotations

WEIGHTS_VERSION = "1.3"

# Documented fusion weights (sum = 1.0). Research-grade classical bank.
DEFAULT_WEIGHTS: dict[str, float] = {
    "metadata": 0.05,
    "provenance": 0.10,  # strong when generative assertions present; ~0 when absent
    "labels": 0.14,  # visible AI disclosures in pixels (screenshot path)
    "ela": 0.09,
    "fft": 0.10,  # Durall azimuthal / log-log spectrum
    "dct": 0.07,
    "noise": 0.07,
    "srm": 0.11,  # Fridrich & Kodovský SRM residual bank (TRIDENT spectral path)
    "bayar": 0.07,  # constrained prediction residual
    "local_corr": 0.09,  # NPR / ForenAgent local-correlation upsampling cues
    "texture": 0.07,
    "screenshot": 0.04,
}

assert abs(sum(DEFAULT_WEIGHTS.values()) - 1.0) < 1e-9, "DEFAULT_WEIGHTS must sum to 1.0"

# Back-compat alias for tests / docs
WEIGHTS = DEFAULT_WEIGHTS

__all__ = ["DEFAULT_WEIGHTS", "WEIGHTS", "WEIGHTS_VERSION"]
