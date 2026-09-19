import io
import struct
from pathlib import Path

import numpy as np
from PIL import Image, PngImagePlugin

from ai_image_authenticator.application.analyzers.labels import VisibleLabelOCR
from ai_image_authenticator.application.analyzers.metadata import MetadataForensics
from ai_image_authenticator.application.analyzers.screenshot import ScreenshotHeuristic
from ai_image_authenticator.container import create_container
from ai_image_authenticator.domain.verdict import verdict_from_probability

SAMPLES = Path(__file__).resolve().parents[3] / "samples"


def _png_bytes(arr: np.ndarray, text: dict | None = None) -> bytes:
    img = Image.fromarray(arr.astype(np.uint8), mode="RGB")
    buf = io.BytesIO()
    if text:
        meta = PngImagePlugin.PngInfo()
        for k, v in text.items():
            meta.add_text(k, v)
        img.save(buf, format="PNG", pnginfo=meta)
    else:
        img.save(buf, format="PNG")
    return buf.getvalue()


class FakeOcr:
    def __init__(self, text: str) -> None:
        self._text = text

    def is_available(self) -> bool:
        return True

    def image_to_string(self, image, config: str = "--psm 6") -> str:
        return self._text


def test_metadata_detects_ai_software_tag():
    arr = np.random.randint(0, 255, (64, 64, 3), dtype=np.uint8)
    data = _png_bytes(arr, {"Software": "Stable Diffusion", "Comment": "Made with AI"})
    img = Image.open(io.BytesIO(data))
    rgb = np.asarray(img.convert("RGB"))
    out = MetadataForensics().analyze(img, rgb, data, "gen.png")
    assert out.score >= 0.7
    assert any("AI" in f or "Stable" in f for f in out.findings)


def test_labels_ocr_handles_al_a1_slip():
    arr = np.random.randint(0, 255, (64, 64, 3), dtype=np.uint8)
    data = _png_bytes(arr)
    img = Image.open(io.BytesIO(data))
    rgb = np.asarray(img.convert("RGB"))
    # Simulate OCR reading "Made with Al" (I→l) / "A1"
    out = VisibleLabelOCR(ocr=FakeOcr("Badge: Made with Al · Generated with A1")).analyze(
        img, rgb, data, "badge.png"
    )
    assert out.score >= 0.88
    assert out.details.get("ai_label_hits")
    assert any("Made with AI" in h for h in out.details["ai_label_hits"])


def test_pipeline_on_synthetic_smooth_image():
    yy, xx = np.mgrid[0:128, 0:128]
    arr = np.stack(
        [
            (xx * 2).astype(np.uint8),
            (yy * 2).astype(np.uint8),
            np.full((128, 128), 180, dtype=np.uint8),
        ],
        axis=-1,
    )
    data = _png_bytes(arr)
    service = create_container().analysis_service
    result = service.analyze_bytes(data, "smooth.png")
    assert result.verdict == verdict_from_probability(result.ai_probability)
    assert 0.0 <= result.ai_probability <= 1.0
    assert len(result.signals) == 12
    assert result.dimensions == [128, 128]


def test_screenshot_heuristic_on_ui_like_image():
    arr = np.full((400, 300, 3), 245, dtype=np.uint8)
    arr[60:, :, :] = np.random.randint(40, 200, (340, 300, 3), dtype=np.uint8)
    arr[:40, :, :] = 30
    data = _png_bytes(arr)
    img = Image.open(io.BytesIO(data))
    rgb = np.asarray(img.convert("RGB"))
    out = ScreenshotHeuristic().analyze(img, rgb, data, "screenshot-tweet.png")
    assert out.details["screenshot_likelihood"] >= 0.35


def test_screenshot_heuristic_fires_on_screenshot_fixture():
    data = (SAMPLES / "synthetic-screenshot.png").read_bytes()
    img = Image.open(io.BytesIO(data))
    rgb = np.asarray(img.convert("RGB"))
    out = ScreenshotHeuristic().analyze(img, rgb, data, "synthetic-screenshot.png")
    assert out.details["is_screenshot"] is True
    assert out.details["chrome_cues"] >= 2


def test_screenshot_heuristic_ignores_flat_art_without_chrome():
    # Regression for 86f8230: flat synthetic art has uniform borders but no UI chrome
    yy, xx = np.mgrid[0:256, 0:256]
    arr = np.stack([xx, yy, np.full_like(xx, 160)], -1).astype(np.uint8)
    data = _png_bytes(arr)
    img = Image.open(io.BytesIO(data))
    rgb = np.asarray(img.convert("RGB"))
    out = ScreenshotHeuristic().analyze(img, rgb, data, "art.png")
    assert out.details["is_screenshot"] is False


def test_registry_open_closed():
    from ai_image_authenticator.application.analyzers.metadata import MetadataForensics
    from ai_image_authenticator.application.analyzers.registry import AnalyzerRegistry

    reg = AnalyzerRegistry()
    reg.register(MetadataForensics())
    assert reg.ids() == ["metadata"]

def test_provenance_absent_on_plain_png():
    from ai_image_authenticator.application.analyzers.provenance import ProvenanceC2PA

    arr = np.random.randint(0, 255, (48, 48, 3), dtype=np.uint8)
    data = _png_bytes(arr)
    img = Image.open(io.BytesIO(data))
    rgb = np.asarray(img.convert("RGB"))
    out = ProvenanceC2PA(use_c2pa_reader=False).analyze(img, rgb, data, "plain.png")
    assert out.id == "provenance"
    assert out.details.get("manifest_present") is False
    assert out.details.get("ai_digital_source_types") == []
    assert any("No C2PA" in f for f in out.findings)
    assert out.details.get("path") == "provenance_contract"


def test_provenance_detects_cabx_and_trained_algorithmic_media():
    from ai_image_authenticator.application.analyzers.provenance import ProvenanceC2PA

    arr = np.random.randint(0, 255, (32, 32, 3), dtype=np.uint8)
    base = _png_bytes(arr)
    iend = base.rfind(b"IEND")
    assert iend > 0
    payload = b"c2pa.manifest.mock" + (
        b"http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia"
    )
    chunk = struct.pack(">I", len(payload)) + b"caBX" + payload + b"\x00\x00\x00\x00"
    splice_at = iend - 4
    forged = base[:splice_at] + chunk + base[splice_at:]
    img = Image.open(io.BytesIO(base))
    rgb = np.asarray(img.convert("RGB"))
    out = ProvenanceC2PA(use_c2pa_reader=False).analyze(img, rgb, forged, "cred.png")
    assert out.details.get("png_cabx_chunk") is True
    assert out.details.get("manifest_present") is True
    assert "trainedAlgorithmicMedia" in out.details.get("ai_digital_source_types", [])
    assert out.score >= 0.85


def test_provenance_detects_jpeg_app11_jumbf_markers():
    from ai_image_authenticator.application.analyzers.provenance import ProvenanceC2PA

    payload = b"JUMBF\x00c2pa-store-mock"
    app11 = b"\xff\xeb" + struct.pack(">H", len(payload) + 2) + payload
    jpeg = b"\xff\xd8" + app11 + b"\xff\xd9"
    img = Image.new("RGB", (16, 16), color=(10, 20, 30))
    rgb = np.asarray(img)
    out = ProvenanceC2PA(use_c2pa_reader=False).analyze(img, rgb, jpeg, "cred.jpg")
    assert out.details.get("jpeg_jumbf_app11") is True
    assert out.details.get("manifest_present") is True


def test_pipeline_includes_provenance_signal():
    arr = np.random.randint(0, 255, (64, 64, 3), dtype=np.uint8)
    data = _png_bytes(arr)
    result = create_container().analysis_service.analyze_bytes(data, "x.png")
    ids = {s.id for s in result.signals}
    assert "provenance" in ids
    assert result.evidence_paths
    assert result.fusion_reasons


def test_labels_ocr_more_disclosure_phrases():
    arr = np.random.randint(0, 255, (64, 64, 3), dtype=np.uint8)
    data = _png_bytes(arr)
    img = Image.open(io.BytesIO(data))
    rgb = np.asarray(img.convert("RGB"))
    out = VisibleLabelOCR(ocr=FakeOcr("Created with AI · Content Credentials · Grok")).analyze(
        img, rgb, data, "more.png"
    )
    assert out.score >= 0.88
    hits = out.details.get("ai_label_hits") or []
    assert any("Created with AI" in h for h in hits)
    assert out.details.get("hit_confidences")


def test_provenance_extracts_actions_and_generators():
    from ai_image_authenticator.application.analyzers.provenance import ProvenanceC2PA

    arr = np.random.randint(0, 255, (32, 32, 3), dtype=np.uint8)
    base = _png_bytes(arr)
    iend = base.rfind(b"IEND")
    payload = (
        b"c2pa.created softwareAgent=OpenAI Media Service "
        b"c2pa.watermarked.unbound "
        b"http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia"
    )
    chunk = struct.pack(">I", len(payload)) + b"caBX" + payload + b"\x00\x00\x00\x00"
    forged = base[: iend - 4] + chunk + base[iend - 4 :]
    img = Image.open(io.BytesIO(base))
    rgb = np.asarray(img.convert("RGB"))
    out = ProvenanceC2PA(use_c2pa_reader=False).analyze(img, rgb, forged, "rich.png")
    assert out.details.get("soft_binding_hint") is True
    assert out.details.get("assertion_richness", 0) >= 1
    assert out.score >= 0.85


def test_fft_reports_anisotropy_fields():
    from ai_image_authenticator.application.analyzers.fft import FrequencySpectrum

    yy, xx = np.mgrid[0:128, 0:128]
    arr = np.stack([(xx * 2).astype(np.uint8), (yy * 2).astype(np.uint8), np.full((128, 128), 100, np.uint8)], -1)
    data = _png_bytes(arr)
    img = Image.open(io.BytesIO(data))
    rgb = np.asarray(img.convert("RGB"))
    out = FrequencySpectrum().analyze(img, rgb, data, "fft.png")
    assert "hf_lf_ratio" in out.details
    assert "azimuthal_anisotropy" in out.details
    assert "spectral_kurtosis" in out.details


def test_ela_multi_quality_details():
    from ai_image_authenticator.application.analyzers.ela import ErrorLevelAnalysis

    arr = np.full((96, 96, 3), 180, dtype=np.uint8)
    data = _png_bytes(arr)
    img = Image.open(io.BytesIO(data))
    rgb = np.asarray(img.convert("RGB"))
    out = ErrorLevelAnalysis().analyze(img, rgb, data, "ela.png")
    assert "mean_residual_q75" in out.details
    assert "edge_flat_ratio" in out.details


def test_registry_includes_research_analyzers():
    ids = create_container().analyzer_ids
    assert "srm" in ids
    assert "bayar" in ids
    assert "local_corr" in ids
    assert len(ids) == 12


def test_srm_analyzer_emits_residual_stats():
    from ai_image_authenticator.application.analyzers.srm import SRMResidualAnalyzer

    arr = np.random.randint(0, 255, (96, 96, 3), dtype=np.uint8)
    data = _png_bytes(arr)
    img = Image.open(io.BytesIO(data))
    rgb = np.asarray(img.convert("RGB"))
    out = SRMResidualAnalyzer().analyze(img, rgb, data, "srm.png")
    assert out.id == "srm"
    assert out.visualization
    assert "mean_abs_residual" in out.details
    assert "per_filter" in out.details
    assert 0.0 <= out.score <= 1.0


def test_bayar_analyzer_emits_prediction_map():
    from ai_image_authenticator.application.analyzers.bayar import BayarPredictionResidual

    arr = np.random.randint(0, 255, (96, 96, 3), dtype=np.uint8)
    data = _png_bytes(arr)
    img = Image.open(io.BytesIO(data))
    rgb = np.asarray(img.convert("RGB"))
    out = BayarPredictionResidual().analyze(img, rgb, data, "bayar.png")
    assert out.id == "bayar"
    assert out.visualization
    assert out.details.get("kernel")
    assert "lag1_correlation" in out.details


def test_local_corr_analyzer_npr_energy():
    from ai_image_authenticator.application.analyzers.local_corr import LocalCorrelationAnalyzer

    arr = np.random.randint(0, 255, (96, 96, 3), dtype=np.uint8)
    data = _png_bytes(arr)
    img = Image.open(io.BytesIO(data))
    rgb = np.asarray(img.convert("RGB"))
    out = LocalCorrelationAnalyzer().analyze(img, rgb, data, "lc.png")
    assert out.id == "local_corr"
    assert out.visualization
    assert "npr_energy_x2" in out.details
    assert "neighbor_corr" in out.details


def test_fft_reports_durall_spectrum_fields():
    from ai_image_authenticator.application.analyzers.fft import FrequencySpectrum

    yy, xx = np.mgrid[0:128, 0:128]
    arr = np.stack(
        [
            (xx * 2).astype(np.uint8),
            (yy * 2).astype(np.uint8),
            np.full((128, 128), 100, np.uint8),
        ],
        -1,
    )
    data = _png_bytes(arr)
    img = Image.open(io.BytesIO(data))
    rgb = np.asarray(img.convert("RGB"))
    out = FrequencySpectrum().analyze(img, rgb, data, "fft2.png")
    assert "log_log_slope" in out.details
    assert "hf_power_ratio" in out.details
    assert "azimuthal_spike_fraction" in out.details
    assert "azimuthal_avg_power_ds" in out.details


def test_srm_elevated_on_smooth_synthetic():
    from ai_image_authenticator.application.analyzers.srm import SRMResidualAnalyzer

    yy, xx = np.mgrid[0:128, 0:128]
    arr = np.stack(
        [
            (xx * 2).astype(np.uint8),
            (yy * 2).astype(np.uint8),
            np.full((128, 128), 180, dtype=np.uint8),
        ],
        axis=-1,
    )
    data = _png_bytes(arr)
    img = Image.open(io.BytesIO(data))
    rgb = np.asarray(img.convert("RGB"))
    out = SRMResidualAnalyzer().analyze(img, rgb, data, "smooth.png")
    assert out.score >= 0.55


def test_pipeline_signal_count_research_grade():
    arr = np.random.randint(0, 255, (64, 64, 3), dtype=np.uint8)
    data = _png_bytes(arr)
    result = create_container().analysis_service.analyze_bytes(data, "x.png")
    assert len(result.signals) == 12
