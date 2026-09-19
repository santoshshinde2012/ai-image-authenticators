"""Weights single-source-of-truth checks."""

from __future__ import annotations

from ai_image_authenticator.application.services import fusion, weights
from ai_image_authenticator.application.services.weights import DEFAULT_WEIGHTS, WEIGHTS_VERSION


def test_default_weights_sum_to_one() -> None:
    assert abs(sum(DEFAULT_WEIGHTS.values()) - 1.0) < 1e-9


def test_twelve_weight_keys() -> None:
    expected = {
        "metadata",
        "provenance",
        "labels",
        "ela",
        "fft",
        "dct",
        "noise",
        "srm",
        "bayar",
        "local_corr",
        "texture",
        "screenshot",
    }
    assert set(DEFAULT_WEIGHTS) == expected


def test_fusion_reexports_same_object() -> None:
    assert fusion.DEFAULT_WEIGHTS is weights.DEFAULT_WEIGHTS
    assert fusion.WEIGHTS is weights.WEIGHTS


def test_weights_version_semver_like() -> None:
    assert WEIGHTS_VERSION == "1.3"
