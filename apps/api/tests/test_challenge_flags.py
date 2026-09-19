"""Tests for compression-laundering and signal-conflict challenge calibration."""

from __future__ import annotations

from ai_image_authenticator.application.services.challenge_flags import (
    LAUNDERING_SENSITIVE_IDS,
    assess_challenges,
    estimate_compression_laundering,
)
from ai_image_authenticator.application.services.fusion import WeightedFusionPolicy
from ai_image_authenticator.application.services.weights import DEFAULT_WEIGHTS
from ai_image_authenticator.domain.models import AnalyzerOutput


def _base_outputs() -> list[AnalyzerOutput]:
    return [
        AnalyzerOutput(
            id="metadata",
            name="m",
            score=0.4,
            confidence=0.5,
            findings=[],
            details={"has_camera": False, "has_exif": False},
        ),
        AnalyzerOutput(
            id="provenance",
            name="p",
            score=0.45,
            confidence=0.4,
            findings=[],
            details={"manifest_present": False, "ai_digital_source_types": []},
        ),
        AnalyzerOutput(
            id="labels",
            name="l",
            score=0.42,
            confidence=0.4,
            findings=[],
            details={"ai_label_hits": []},
        ),
        AnalyzerOutput(
            id="ela",
            name="e",
            score=0.4,
            confidence=0.5,
            findings=[],
            details={"mean_residual": 2.0, "spatial_cv": 0.5, "quality_delta": 0.5},
        ),
        AnalyzerOutput(id="fft", name="f", score=0.4, confidence=0.5, findings=[], details={}),
        AnalyzerOutput(
            id="dct",
            name="d",
            score=0.4,
            confidence=0.5,
            findings=[],
            details={"ac_periodicity": 0.1},
        ),
        AnalyzerOutput(id="noise", name="n", score=0.4, confidence=0.5, findings=[], details={}),
        AnalyzerOutput(id="srm", name="srm", score=0.4, confidence=0.5, findings=[], details={}),
        AnalyzerOutput(id="bayar", name="b", score=0.4, confidence=0.5, findings=[], details={}),
        AnalyzerOutput(
            id="local_corr", name="lc", score=0.4, confidence=0.5, findings=[], details={}
        ),
        AnalyzerOutput(id="texture", name="t", score=0.4, confidence=0.5, findings=[], details={}),
        AnalyzerOutput(
            id="screenshot",
            name="s",
            score=0.4,
            confidence=0.5,
            findings=[],
            details={"is_screenshot": False},
        ),
    ]


def _replace(outputs: list[AnalyzerOutput], analyzer_id: str, out: AnalyzerOutput) -> list[AnalyzerOutput]:
    return [out if o.id == analyzer_id else o for o in outputs]


def test_estimate_laundering_high_on_periodicity_and_screenshot():
    by_id = {o.id: o for o in _base_outputs()}
    by_id["dct"] = AnalyzerOutput(
        id="dct",
        name="d",
        score=0.5,
        confidence=0.5,
        findings=[],
        details={"ac_periodicity": 0.42},
    )
    by_id["screenshot"] = AnalyzerOutput(
        id="screenshot",
        name="s",
        score=0.7,
        confidence=0.7,
        findings=[],
        details={"is_screenshot": True},
    )
    by_id["ela"] = AnalyzerOutput(
        id="ela",
        name="e",
        score=0.5,
        confidence=0.5,
        findings=[],
        details={"mean_residual": 4.0, "spatial_cv": 1.2, "quality_delta": 2.0},
    )
    score, notes = estimate_compression_laundering(by_id)
    assert score >= 0.45
    assert notes


def test_fusion_sets_compression_laundering_and_dampens_spectral_weights():
    outputs = _base_outputs()
    outputs = _replace(
        outputs,
        "dct",
        AnalyzerOutput(
            id="dct",
            name="d",
            score=0.55,
            confidence=0.6,
            findings=["periodicity"],
            details={"ac_periodicity": 0.5},
        ),
    )
    outputs = _replace(
        outputs,
        "screenshot",
        AnalyzerOutput(
            id="screenshot",
            name="s",
            score=0.7,
            confidence=0.7,
            findings=[],
            details={"is_screenshot": True},
        ),
    )
    outputs = _replace(
        outputs,
        "ela",
        AnalyzerOutput(
            id="ela",
            name="e",
            score=0.5,
            confidence=0.5,
            findings=[],
            details={"mean_residual": 4.2, "spatial_cv": 1.3, "quality_delta": 2.1},
        ),
    )
    outputs = _replace(
        outputs,
        "fft",
        AnalyzerOutput(id="fft", name="f", score=0.85, confidence=0.9, findings=["hot"], details={}),
    )
    outputs = _replace(
        outputs,
        "srm",
        AnalyzerOutput(id="srm", name="srm", score=0.85, confidence=0.9, findings=["hot"], details={}),
    )

    outcome = WeightedFusionPolicy().fuse(outputs, {}, "launder.png", [64, 64], 10)
    assert "compression_laundering" in outcome.challenge_flags
    assert any("compression_laundering" in r for r in outcome.fusion_reasons)
    for sid in ("fft", "srm", "dct"):
        sig = next(s for s in outcome.signals if s.id == sid)
        assert sig.weight < DEFAULT_WEIGHTS[sid]
        assert sid in LAUNDERING_SENSITIVE_IDS


def test_provenance_vs_pixels_conflict_reduces_confidence():
    outs: list[AnalyzerOutput] = []
    pixel_ids = {"ela", "fft", "dct", "noise", "texture", "srm", "bayar", "local_corr"}
    for o in _base_outputs():
        if o.id == "labels":
            outs.append(
                AnalyzerOutput(
                    id="labels",
                    name="l",
                    score=0.95,
                    confidence=0.92,
                    findings=["Made with AI"],
                    details={"ai_label_hits": ["Made with AI"]},
                )
            )
        elif o.id in pixel_ids:
            outs.append(
                AnalyzerOutput(
                    id=o.id, name=o.name, score=0.2, confidence=0.75, findings=["real"], details={}
                )
            )
        elif o.id == "metadata":
            outs.append(
                AnalyzerOutput(
                    id="metadata",
                    name="m",
                    score=0.2,
                    confidence=0.7,
                    findings=[],
                    details={"has_camera": False, "has_exif": False},
                )
            )
        else:
            outs.append(o)

    outcome = WeightedFusionPolicy().fuse(outs, {}, "conflict.png", [32, 32], 8)
    assert "provenance_vs_pixels_conflict" in outcome.challenge_flags
    assert "signal_disagreement" in outcome.challenge_flags
    assert any("provenance_vs_pixels_conflict" in r for r in outcome.fusion_reasons)
    assert outcome.ai_probability >= 0.55
    assert outcome.confidence < 0.9


def test_camera_exif_with_strong_ai_forensics_flag():
    outs: list[AnalyzerOutput] = []
    pixel_ids = {"ela", "fft", "dct", "noise", "texture", "srm", "bayar", "local_corr"}
    for o in _base_outputs():
        if o.id == "metadata":
            outs.append(
                AnalyzerOutput(
                    id="metadata",
                    name="m",
                    score=0.15,
                    confidence=0.7,
                    findings=["Camera"],
                    details={"has_camera": True, "has_exif": True},
                )
            )
        elif o.id in pixel_ids:
            outs.append(
                AnalyzerOutput(
                    id=o.id, name=o.name, score=0.72, confidence=0.75, findings=["ai"], details={}
                )
            )
        else:
            outs.append(o)

    outcome = WeightedFusionPolicy().fuse(outs, {}, "cam.png", [32, 32], 8)
    assert "possible_overprocessed_camera_photo" in outcome.challenge_flags
    assert "signal_disagreement" in outcome.challenge_flags
    assert outcome.confidence < 0.85


def test_assess_challenges_helper_direct():
    by_id = {o.id: o for o in _base_outputs()}
    by_id["metadata"] = AnalyzerOutput(
        id="metadata",
        name="m",
        score=0.1,
        confidence=0.7,
        findings=[],
        details={"has_camera": True},
    )
    assessment = assess_challenges(
        by_id,
        provenance_ai=False,
        visible_ai_label=False,
        mean_forensic=0.7,
        lean_ai=5,
        lean_real=0,
        forensic_count=9,
    )
    assert "possible_overprocessed_camera_photo" in assessment.flags


def test_challenge_flags_default_empty_when_clean():
    outcome = WeightedFusionPolicy().fuse(_base_outputs(), {}, "clean.png", [32, 32], 5)
    assert outcome.challenge_flags == []
