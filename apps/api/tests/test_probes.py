"""Tests for JPEG degradation probes and AnalysisService probe wiring."""

from __future__ import annotations

import io

import numpy as np
from PIL import Image

from ai_image_authenticator.application.analyzers.dct import DCTJpegStats
from ai_image_authenticator.application.analyzers.ela import ErrorLevelAnalysis
from ai_image_authenticator.application.analyzers.fft import FrequencySpectrum
from ai_image_authenticator.application.services.analysis import AnalysisService
from ai_image_authenticator.application.services.fusion import WeightedFusionPolicy
from ai_image_authenticator.application.services.probes import (
    PROBE_ANALYZER_IDS,
    build_probe_output,
    forensic_lean,
    jpeg_reencode,
)
from ai_image_authenticator.container import build_content_analyzers, build_registry
from ai_image_authenticator.domain.models import AnalyzerOutput
from ai_image_authenticator.infrastructure.artifact_store import InMemoryArtifactStore


def _rgb(size: int = 64) -> np.ndarray:
    rng = np.random.default_rng(0)
    return rng.integers(0, 255, size=(size, size, 3), dtype=np.uint8)


def test_jpeg_reencode_roundtrip():
    rgb = _rgb(48)
    img, arr, raw = jpeg_reencode(rgb, 75)
    assert img.size == (48, 48)
    assert arr.shape == (48, 48, 3)
    assert raw[:2] == b"\xff\xd8"


def test_build_probe_output_shape():
    rgb = _rgb(48)
    clean = {
        "ela": AnalyzerOutput(id="ela", name="e", score=0.6, confidence=0.5, findings=[], details={}),
        "fft": AnalyzerOutput(id="fft", name="f", score=0.6, confidence=0.5, findings=[], details={}),
        "dct": AnalyzerOutput(id="dct", name="d", score=0.6, confidence=0.5, findings=[], details={}),
        "srm": AnalyzerOutput(id="srm", name="s", score=0.6, confidence=0.5, findings=[], details={}),
        "bayar": AnalyzerOutput(id="bayar", name="b", score=0.6, confidence=0.5, findings=[], details={}),
        "local_corr": AnalyzerOutput(
            id="local_corr", name="l", score=0.6, confidence=0.5, findings=[], details={}
        ),
        "noise": AnalyzerOutput(id="noise", name="n", score=0.6, confidence=0.5, findings=[], details={}),
    }
    probes = [ErrorLevelAnalysis(), FrequencySpectrum(), DCTJpegStats()]
    out = build_probe_output(
        clean_by_id=clean, probe_analyzers=probes, rgb=rgb, filename="t.png"
    )
    assert out.id == "_probes"
    assert out.details.get("laundering_probe") is True
    assert "jpeg_q75" in out.details
    assert "jpeg_q85" in out.details
    # Clean and degraded means must cover the same analyzers (only those the bank can re-run)
    ran = sorted({"ela", "fft"})
    assert out.details["probe_ids"] == ran
    assert sorted(out.details["clean"]["scores"]) == ran
    assert sorted(out.details["jpeg_q75"]["scores"]) == ran
    lean = forensic_lean(list(clean.values()))
    assert lean["count"] == len(PROBE_ANALYZER_IDS)


def test_analysis_service_includes_probe_flags_path():
    reg = build_registry()
    content = build_content_analyzers()
    svc = AnalysisService(
        analyzers=reg.all(),
        fusion=WeightedFusionPolicy(),
        artifacts=InMemoryArtifactStore(),
        content_analyzers=content,
        probe_analyzers=content,
        enable_probes=True,
    )
    buf = io.BytesIO()
    Image.fromarray(_rgb(64), mode="RGB").save(buf, format="PNG")
    outcome = svc.analyze_bytes(buf.getvalue(), "probe.png")
    assert "laundering_probe" in outcome.challenge_flags
    # failure_modes always populated from static catalog
    assert len(outcome.failure_modes) >= 1
    assert all(s.id != "_probes" for s in outcome.signals)
