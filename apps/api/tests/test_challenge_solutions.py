"""Additional challenge solution tests (dual-layer, probes, failure_modes)."""

from __future__ import annotations

from ai_image_authenticator.application.services.challenge_flags import (
    STATIC_FAILURE_MODES,
    build_failure_modes,
)
from ai_image_authenticator.application.services.fusion import WeightedFusionPolicy
from ai_image_authenticator.domain.models import AnalyzerOutput


def _base_outputs() -> list[AnalyzerOutput]:
    return [
        AnalyzerOutput(id="metadata", name="m", score=0.4, confidence=0.5, findings=[], details={"has_camera": False, "has_exif": False}),
        AnalyzerOutput(id="provenance", name="p", score=0.45, confidence=0.4, findings=[], details={"manifest_present": False, "ai_digital_source_types": []}),
        AnalyzerOutput(id="labels", name="l", score=0.42, confidence=0.4, findings=[], details={"ai_label_hits": []}),
        AnalyzerOutput(id="ela", name="e", score=0.4, confidence=0.5, findings=[], details={"mean_residual": 2.0, "spatial_cv": 0.5, "quality_delta": 0.5}),
        AnalyzerOutput(id="fft", name="f", score=0.4, confidence=0.5, findings=[], details={}),
        AnalyzerOutput(id="dct", name="d", score=0.4, confidence=0.5, findings=[], details={"ac_periodicity": 0.1}),
        AnalyzerOutput(id="noise", name="n", score=0.4, confidence=0.5, findings=[], details={}),
        AnalyzerOutput(id="srm", name="srm", score=0.4, confidence=0.5, findings=[], details={}),
        AnalyzerOutput(id="bayar", name="b", score=0.4, confidence=0.5, findings=[], details={}),
        AnalyzerOutput(id="local_corr", name="lc", score=0.4, confidence=0.5, findings=[], details={}),
        AnalyzerOutput(id="texture", name="t", score=0.4, confidence=0.5, findings=[], details={}),
        AnalyzerOutput(id="screenshot", name="s", score=0.4, confidence=0.5, findings=[], details={"is_screenshot": False}),
    ]


def _replace(outputs, analyzer_id, out):
    return [out if o.id == analyzer_id else o for o in outputs]


def test_dual_layer_and_synthid_flags():
    outs = _base_outputs()
    outs = _replace(
        outs,
        "provenance",
        AnalyzerOutput(
            id="provenance",
            name="p",
            score=0.5,
            confidence=0.7,
            findings=["soft binding"],
            details={
                "manifest_present": True,
                "ai_digital_source_types": [],
                "soft_binding_hint": True,
                "action_labels": ["c2pa.watermarked.unbound"],
                "raw_markers": {"has_soft_binding_hint": True},
            },
        ),
    )
    outcome = WeightedFusionPolicy().fuse(outs, {}, "dual.png", [32, 32], 8)
    assert "dual_layer_provenance_hint" in outcome.challenge_flags
    assert "synthid_layer_not_verified" in outcome.challenge_flags
    assert outcome.failure_modes
    assert any("SynthID" in m or "synthid" in m.lower() for m in outcome.failure_modes)


def test_transform_bias_and_srm_flags_with_laundering():
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
    outcome = WeightedFusionPolicy().fuse(outputs, {}, "launder.png", [64, 64], 10)
    assert "compression_laundering" in outcome.challenge_flags
    assert "transform_bias_risk" in outcome.challenge_flags
    assert "frequency_srm_brittleness" in outcome.challenge_flags
    assert any("laundering" in m.lower() or "transform" in m.lower() for m in outcome.failure_modes)


def test_probe_output_sets_laundering_probe_and_shift_flags():
    outs = _base_outputs()
    for pid in ("ela", "fft", "dct", "srm", "bayar", "local_corr", "noise"):
        outs = _replace(
            outs,
            pid,
            AnalyzerOutput(
                id=pid, name=pid, score=0.75, confidence=0.8, findings=["ai"], details={}
            ),
        )
    outs.append(
        AnalyzerOutput(
            id="_probes",
            name="Degradation probes",
            score=0.5,
            confidence=0.5,
            findings=["probe"],
            details={
                "laundering_probe": True,
                "delta_q75": -0.2,
                "delta_q85": -0.15,
                "probe_disagrees_q75": True,
                "probe_disagrees_q85": True,
                "generator_shift_uncertainty": True,
                "jpeg_q75": {"mean": 0.35},
                "jpeg_q85": {"mean": 0.4},
                "clean": {"mean": 0.75},
            },
        )
    )
    outcome = WeightedFusionPolicy().fuse(outs, {}, "shift.png", [64, 64], 12)
    assert "laundering_probe" in outcome.challenge_flags
    assert "generator_shift_uncertainty" in outcome.challenge_flags
    assert any("laundering_probe" in r for r in outcome.fusion_reasons)
    assert outcome.failure_modes
    # Against the same evidence with an agreeing probe, disagreement must cost confidence
    # and pull the probability toward 0.5
    calm = [o for o in outs if o.id != "_probes"] + [
        AnalyzerOutput(
            id="_probes",
            name="Degradation probes",
            score=0.5,
            confidence=0.5,
            findings=["probe"],
            details={"laundering_probe": True, "delta_q75": 0.0, "delta_q85": 0.0},
        )
    ]
    baseline = WeightedFusionPolicy().fuse(calm, {}, "calm.png", [64, 64], 12)
    assert "generator_shift_uncertainty" not in baseline.challenge_flags
    assert outcome.confidence < baseline.confidence
    assert abs(outcome.ai_probability - 0.5) < abs(baseline.ai_probability - 0.5)


def test_failure_modes_always_include_static_catalog():
    modes = build_failure_modes([])
    for s in STATIC_FAILURE_MODES:
        assert s in modes
    modes2 = build_failure_modes(["compression_laundering"])
    assert len(modes2) > len(modes)
