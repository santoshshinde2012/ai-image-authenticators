from ai_image_authenticator.application.services.fusion import WEIGHTS, _verdict, fusion_math


def test_weights_sum_near_one():
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9


def test_fusion_math_weighted_average():
    scores = {k: 0.0 for k in WEIGHTS}
    scores["metadata"] = 1.0
    expected = WEIGHTS["metadata"] / sum(WEIGHTS.values())
    assert abs(fusion_math(scores) - expected) < 1e-9


def test_fusion_math_uniform():
    scores = {k: 0.6 for k in WEIGHTS}
    assert abs(fusion_math(scores) - 0.6) < 1e-9


def test_verdict_bands():
    assert _verdict(0.2) == "real"
    assert _verdict(0.4) == "inconclusive"
    assert _verdict(0.6) == "likely_ai"
    assert _verdict(0.9) == "ai_generated"


def test_fusion_separates_provenance_and_pixel_paths():
    from ai_image_authenticator.application.services.fusion import WeightedFusionPolicy
    from ai_image_authenticator.domain.models import AnalyzerOutput

    outputs = [
        AnalyzerOutput(id="metadata", name="m", score=0.4, confidence=0.5, findings=[], details={}),
        AnalyzerOutput(
            id="provenance",
            name="p",
            score=0.9,
            confidence=0.9,
            findings=["AI source"],
            details={
                "manifest_present": True,
                "ai_digital_source_types": ["trainedAlgorithmicMedia"],
            },
        ),
        AnalyzerOutput(
            id="labels",
            name="l",
            score=0.42,
            confidence=0.4,
            findings=[],
            details={"ai_label_hits": []},
        ),
        AnalyzerOutput(id="ela", name="e", score=0.4, confidence=0.5, findings=[], details={}),
        AnalyzerOutput(id="fft", name="f", score=0.4, confidence=0.5, findings=[], details={}),
        AnalyzerOutput(id="dct", name="d", score=0.4, confidence=0.5, findings=[], details={}),
        AnalyzerOutput(id="noise", name="n", score=0.4, confidence=0.5, findings=[], details={}),
        AnalyzerOutput(id="texture", name="t", score=0.4, confidence=0.5, findings=[], details={}),
        AnalyzerOutput(
            id="screenshot",
            name="s",
            score=0.45,
            confidence=0.5,
            findings=[],
            details={"is_screenshot": False},
        ),
    ]
    outcome = WeightedFusionPolicy().fuse(outputs, {}, "x.png", [10, 10], 12)
    assert "provenance_contract" in outcome.evidence_paths
    assert any("digitalSourceType" in r for r in outcome.fusion_reasons)
    assert outcome.ai_probability >= 0.82


def test_ocr_hard_floor_still_applies():
    from ai_image_authenticator.application.services.fusion import WeightedFusionPolicy
    from ai_image_authenticator.domain.models import AnalyzerOutput

    outputs = [
        AnalyzerOutput(id=i, name=i, score=0.3, confidence=0.5, findings=[], details={})
        for i in ("metadata", "ela", "fft", "dct", "noise", "texture")
    ]
    outputs.append(
        AnalyzerOutput(
            id="provenance",
            name="p",
            score=0.45,
            confidence=0.4,
            findings=[],
            details={"manifest_present": False, "ai_digital_source_types": []},
        )
    )
    outputs.append(
        AnalyzerOutput(
            id="labels",
            name="l",
            score=0.95,
            confidence=0.92,
            findings=["Made with AI"],
            details={"ai_label_hits": ["Made with AI"]},
        )
    )
    outputs.append(
        AnalyzerOutput(
            id="screenshot",
            name="s",
            score=0.5,
            confidence=0.5,
            findings=[],
            details={"is_screenshot": False},
        )
    )
    outcome = WeightedFusionPolicy().fuse(outputs, {}, "badge.png", [10, 10], 5)
    assert outcome.ai_probability >= 0.82
    assert "provenance_contract" in outcome.evidence_paths


def test_absent_c2pa_does_not_dilute_forensics():
    from ai_image_authenticator.application.services.fusion import WeightedFusionPolicy
    from ai_image_authenticator.domain.models import AnalyzerOutput

    outputs = [
        AnalyzerOutput(id="metadata", name="m", score=0.7, confidence=0.6, findings=[], details={}),
        AnalyzerOutput(
            id="provenance",
            name="p",
            score=0.45,
            confidence=0.4,
            findings=["No C2PA"],
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
        AnalyzerOutput(id="ela", name="e", score=0.72, confidence=0.7, findings=[], details={}),
        AnalyzerOutput(id="fft", name="f", score=0.70, confidence=0.7, findings=[], details={}),
        AnalyzerOutput(id="dct", name="d", score=0.68, confidence=0.6, findings=[], details={}),
        AnalyzerOutput(id="noise", name="n", score=0.65, confidence=0.6, findings=[], details={}),
        AnalyzerOutput(id="texture", name="t", score=0.62, confidence=0.6, findings=[], details={}),
        AnalyzerOutput(
            id="screenshot",
            name="s",
            score=0.4,
            confidence=0.5,
            findings=[],
            details={"is_screenshot": False},
        ),
    ]
    outcome = WeightedFusionPolicy().fuse(outputs, {}, "synth.png", [10, 10], 9)
    # Provenance effective weight should be tiny
    prov = next(s for s in outcome.signals if s.id == "provenance")
    assert prov.weight <= 0.02
    assert outcome.ai_probability >= 0.58
    assert "pixel_forensic" in outcome.evidence_paths
    assert any("agreement boost" in r for r in outcome.fusion_reasons)


def test_weights_documented_keys():
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
    assert set(WEIGHTS) == expected


def test_normalize_score_shrinks_low_confidence():
    from ai_image_authenticator.application.services.fusion import _normalize_score

    hot = _normalize_score(0.95, 0.2)
    firm = _normalize_score(0.95, 0.95)
    assert abs(hot - 0.5) < abs(firm - 0.5)
    assert firm > hot
