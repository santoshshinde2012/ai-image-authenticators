"""Regression tests for the bugs recorded in docs/gap-analysis.md."""

from __future__ import annotations

import datetime as dt
import io
import json
import struct

import numpy as np
import pytest
from PIL import Image, PngImagePlugin

from ai_image_authenticator.application.analyzers.dct import DCTJpegStats
from ai_image_authenticator.application.analyzers.labels import (
    VisibleLabelOCR,
    _lines,
    match_disclosures,
)
from ai_image_authenticator.application.analyzers.metadata import MetadataForensics
from ai_image_authenticator.application.analyzers.provenance import ProvenanceC2PA, _png_cabx_chunks
from ai_image_authenticator.application.services.analysis import AnalysisService
from ai_image_authenticator.application.services.fusion import WeightedFusionPolicy
from ai_image_authenticator.application.services.probes import build_probe_output, jpeg_reencode
from ai_image_authenticator.container import create_container
from ai_image_authenticator.domain.models import AnalyzerOutput
from ai_image_authenticator.infrastructure.artifact_store import InMemoryArtifactStore
from ai_image_authenticator.infrastructure.image_loader import load_image_bytes

IPTC = b"http://cv.iptc.org/newscodes/digitalsourcetype/"


def _png(seed: int = 1, size: int = 64, text: dict | None = None) -> bytes:
    arr = np.random.default_rng(seed).integers(0, 255, (size, size, 3), dtype=np.uint8)
    buf = io.BytesIO()
    info = PngImagePlugin.PngInfo()
    for key, value in (text or {}).items():
        info.add_text(key, value)
    Image.fromarray(arr).save(buf, format="PNG", pnginfo=info)
    return buf.getvalue()


def _with_cabx(base: bytes, payload: bytes) -> bytes:
    at = base.rfind(b"IEND") - 4
    return base[:at] + struct.pack(">I", len(payload)) + b"caBX" + payload + b"\0\0\0\0" + base[at:]


def _provenance(data: bytes, reader: bool | None = False) -> dict:
    loaded = load_image_bytes(data, "t.png")
    return ProvenanceC2PA(use_c2pa_reader=reader).analyze(
        loaded.image, loaded.rgb, data, "t.png"
    ).details


# --- P0-1: OCR disclosures ---------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Kendall Edwards, staff photographer",
        "Randall E. Smith",
        "visto dalle finestre",
        "cleared to land on runway 27L",
        "A firefly lit up the summer night",
        "Gemini is the third astrological sign",
        "Grok is a verb coined by Heinlein",
        "Photo by Imagen Studios, Barcelona",
        "Our panel on synthetic media regulation",
        "Read more about Content Credentials",
        "Al Jazeera English",
    ],
)
def test_ordinary_text_is_not_an_ai_disclosure(text):
    hits, _, _ = match_disclosures(_lines([text]), [])
    assert hits == {}


@pytest.mark.parametrize(
    ("text", "label"),
    [
        ("> Made with Al", "Made with AI"),
        ("AI GENERATED", "AI-generated"),
        ("Image created with Midjourney v6", "Midjourney"),
        ("made with gemini", "Gemini"),
        ("rendered using DALL-E 3", "DALL·E"),
    ],
)
def test_real_disclosures_still_match(text, label):
    hits, _, _ = match_disclosures(_lines([text]), [])
    assert label in hits


def test_distinctive_names_count_only_in_badge_regions():
    assert "Midjourney" not in match_disclosures(_lines(["midjourney"]), [])[0]
    assert "Midjourney" in match_disclosures([], _lines(["midjourney"]))[0]
    assert match_disclosures([], _lines(["gemini"]))[0] == {}  # ordinary word, even in a corner


def test_content_credentials_badge_is_provenance_not_ai():
    class Ocr:
        def is_available(self):
            return True

        def image_to_string(self, image, config=""):
            return "Content Credentials"

    data = _png()
    loaded = load_image_bytes(data, "cr.png")
    out = VisibleLabelOCR(ocr=Ocr()).analyze(loaded.image, loaded.rgb, data, "cr.png")
    assert out.details["ai_label_hits"] == []
    assert out.details["provenance_badge_hits"] == ["Content Credentials"]


def test_repeated_ocr_lines_do_not_inflate_confidence():
    once, _, _ = match_disclosures(_lines(["Made with AI"]), [])
    many, votes, _ = match_disclosures(_lines(["Made with AI"] * 20), [])
    assert votes == 20
    assert many == once


def test_metadata_ordinary_words_are_not_generator_fingerprints():
    data = _png(text={"Comment": "Shot at Firefly Grove, Gemini Observatory"})
    loaded = load_image_bytes(data, "c.png")
    out = MetadataForensics().analyze(loaded.image, loaded.rgb, data, "c.png")
    assert out.details["ai_hits"] == []
    data = _png(text={"Software": "Adobe Firefly"})
    loaded = load_image_bytes(data, "s.png")
    out = MetadataForensics().analyze(loaded.image, loaded.rgb, data, "s.png")
    assert out.details["ai_hits"] == ["Adobe Firefly"]


# --- P0-2: provenance ---------------------------------------------------------------------


def test_source_type_outside_a_manifest_is_ignored():
    details = _provenance(_png() + IPTC + b"trainedAlgorithmicMedia")
    assert details["ai_digital_source_types"] == []
    assert details["manifest_present"] is False
    assert details["unbound_source_type_strings"] == ["trainedAlgorithmicMedia"]


def test_appended_source_type_does_not_force_a_verdict():
    service = create_container().analysis_service
    clean = service.analyze_bytes(_png(), "g.png")
    tainted = service.analyze_bytes(_png() + IPTC + b"trainedAlgorithmicMedia", "g.png")
    assert tainted.ai_probability == pytest.approx(clean.ai_probability)
    assert not any("generative assertion" in r for r in tainted.fusion_reasons)


def test_source_type_taxonomy_follows_c2pa_rubric():
    enhanced = _provenance(_with_cabx(_png(), IPTC + b"algorithmicallyEnhanced"))
    assert enhanced["ai_digital_source_types"] == []
    assert enhanced["declared_source_types"] == ["algorithmicallyEnhanced"]
    data_url = _provenance(
        _with_cabx(_png(), b"http://c2pa.org/digitalsourcetype/trainedAlgorithmicData")
    )
    assert data_url["ai_digital_source_types"] == ["trainedAlgorithmicData"]
    art = _provenance(_with_cabx(_png(), IPTC + b"digitalArt"))
    assert art["ai_digital_source_types"] == []
    assert art["possibly_ai_source_types"] == ["digitalArt"]


def test_malformed_container_is_not_trusted_when_reader_is_available(monkeypatch):
    from ai_image_authenticator.application.analyzers import provenance

    monkeypatch.setattr(
        provenance, "_try_c2pa_reader", lambda raw, name: {"library": "c2pa", "manifest_found": False}
    )
    details = _provenance(_with_cabx(_png(), IPTC + b"trainedAlgorithmicMedia"), reader=True)
    assert details["ai_digital_source_types"] == []
    assert details["unverified_source_types"] == ["trainedAlgorithmicMedia"]


def _signed_png(digital_source_type: str) -> bytes:
    # ImportError too: a native wheel that fails to load should skip, not fail
    c2pa = pytest.importorskip("c2pa", exc_type=ImportError)
    x509 = pytest.importorskip("cryptography.x509")
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    now = dt.datetime.now(dt.UTC)

    def name(cn: str):
        # C2PA's certificate profile requires an Organization; without it the claim
        # signature fails validation (claimSignature.mismatch)
        return x509.Name(
            [
                x509.NameAttribute(NameOID.COMMON_NAME, cn),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Test Org"),
            ]
        )

    def usage(sign: bool, cert_sign: bool):
        return x509.KeyUsage(sign, False, False, False, False, cert_sign, cert_sign, False, False)

    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca = (
        x509.CertificateBuilder().subject_name(name("Test CA")).issuer_name(name("Test CA"))
        .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(usage(False, True), critical=True)
        .sign(ca_key, hashes.SHA256())
    )
    key = ec.generate_private_key(ec.SECP256R1())
    leaf = (
        x509.CertificateBuilder().subject_name(name("Test Signer")).issuer_name(ca.subject)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(usage(True, False), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.EMAIL_PROTECTION]), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    chain = leaf.public_bytes(serialization.Encoding.PEM) + ca.public_bytes(serialization.Encoding.PEM)
    key_pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    signer = c2pa.Signer.from_info(c2pa.C2paSignerInfo(b"es256", chain, key_pem, None))
    manifest = {
        "claim_generator_info": [{"name": "test-harness", "version": "1.0"}],
        "assertions": [
            {
                "label": "c2pa.actions",
                "data": {"actions": [{"action": "c2pa.created", "digitalSourceType": digital_source_type}]},
            }
        ],
    }
    dest = io.BytesIO()
    c2pa.Builder.from_json(json.dumps(manifest)).sign(signer, "image/png", io.BytesIO(_png()), dest)
    return dest.getvalue()


def test_signed_manifest_validates_and_tampering_is_caught():
    signed = _signed_png(IPTC.decode() + "trainedAlgorithmicMedia")
    details = _provenance(signed, reader=True)
    assert details["validation_state"] == "Valid"
    assert details["crypto_validated"] is True
    assert details["trusted"] is False  # no trust list configured
    assert details["ai_digital_source_types"] == ["trainedAlgorithmicMedia"]

    tampered = _with_cabx(_png(seed=99), _png_cabx_chunks(signed)[0])
    details = _provenance(tampered, reader=True)
    assert details["validation_state"] == "Invalid"
    assert details["ai_digital_source_types"] == []
    assert details["unverified_source_types"] == ["trainedAlgorithmicMedia"]


def test_signed_capture_manifest_is_not_generative():
    details = _provenance(_signed_png(IPTC.decode() + "digitalCapture"), reader=True)
    assert details["crypto_validated"] is True
    assert details["ai_digital_source_types"] == []
    assert "digitalCapture" in details["declared_source_types"]


# --- P0-3: DCT lattice --------------------------------------------------------------------


def test_dct_periodicity_is_not_a_resize_artifact():
    rng = np.random.default_rng(3)
    n = 1400
    base = np.repeat((np.mgrid[0:n, 0:n][1] * 255 // n).astype(np.float64)[:, :, None], 3, 2)
    grain = np.clip(base + rng.normal(0, 12, (n, n, 3)), 0, 255).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(grain).save(buf, format="JPEG", quality=80)
    data = buf.getvalue()
    loaded = load_image_bytes(data, "grain.jpg")
    out = DCTJpegStats().analyze(loaded.image, loaded.rgb, data, "grain.jpg")
    # Before the fix this was ~0.82 and added +0.35 to the laundering score
    assert out.details["ac_periodicity"] < 0.22


# --- Probes -------------------------------------------------------------------------------


def test_probe_reencodes_are_reported_as_jpeg():
    img, _, _ = jpeg_reencode(np.zeros((32, 32, 3), dtype=np.uint8), 75)
    assert img.format == "JPEG"


def test_q85_lean_flip_is_detected_without_a_large_delta():
    class Fixed:
        def __init__(self, analyzer_id: str, score: float):
            self.id = analyzer_id
            self._score = score

        def analyze(self, image, rgb, raw, filename):
            return AnalyzerOutput(id=self.id, name=self.id, score=self._score, confidence=0.5)

    clean = {"ela": AnalyzerOutput(id="ela", name="e", score=0.33, confidence=0.5)}
    out = build_probe_output(
        clean_by_id=clean,
        probe_analyzers=[Fixed("ela", 0.40)],  # 0.33 (real-leaning) -> 0.40, delta 0.07
        rgb=np.zeros((32, 32, 3), dtype=np.uint8),
        filename="x.png",
    )
    assert out.details["probe_disagrees_q85"] is False  # no flip: 0.40 is not AI-leaning
    out = build_probe_output(
        clean_by_id={"ela": AnalyzerOutput(id="ela", name="e", score=0.34, confidence=0.5)},
        probe_analyzers=[Fixed("ela", 0.59)],
        rgb=np.zeros((32, 32, 3), dtype=np.uint8),
        filename="x.png",
    )
    assert out.details["probe_disagrees_q85"] is True


# --- Fusion floors ------------------------------------------------------------------------


def _pixel_outputs(score: float) -> list[AnalyzerOutput]:
    ids = ("metadata", "ela", "fft", "dct", "noise", "srm", "bayar", "local_corr", "texture")
    return [AnalyzerOutput(id=i, name=i, score=score, confidence=0.6) for i in ids]


def test_badge_floor_scales_with_ocr_confidence_and_is_capped():
    def fuse(best: float):
        labels = AnalyzerOutput(
            id="labels",
            name="l",
            score=0.9,
            confidence=best,
            details={"ai_label_hits": ["Made with AI"], "hit_confidences": {"Made with AI": best}},
        )
        return WeightedFusionPolicy().fuse(_pixel_outputs(0.2) + [labels], {}, "b.png", [64, 64], 1)

    assert fuse(0.80).ai_probability == pytest.approx(0.91)  # 0.75 + 0.2 * 0.80
    assert fuse(0.98).ai_probability == pytest.approx(0.92)  # capped


def test_conflict_keeps_the_badge_floor():
    labels = AnalyzerOutput(
        id="labels",
        name="l",
        score=0.9,
        confidence=0.95,
        details={"ai_label_hits": ["Made with AI"], "hit_confidences": {"Made with AI": 0.95}},
    )
    outcome = WeightedFusionPolicy().fuse(_pixel_outputs(0.2) + [labels], {}, "c.png", [64, 64], 1)
    assert "provenance_vs_pixels_conflict" in outcome.challenge_flags
    assert outcome.ai_probability >= 0.82
    assert outcome.confidence < 0.9


def test_content_region_pass_merges_only_stronger_crop_evidence():
    class Shot:
        id = "screenshot"

        def analyze(self, image, rgb, raw, filename):
            return AnalyzerOutput(
                id="screenshot", name="s", score=0.52, confidence=0.75, details={"is_screenshot": True}
            )

    class ByShape:
        """Scores the full frame low and the (smaller) content crop high."""

        def __init__(self, analyzer_id: str):
            self.id = analyzer_id

        def analyze(self, image, rgb, raw, filename):
            full = rgb.shape[0] == 200
            return AnalyzerOutput(
                id=self.id,
                name=self.id,
                score=0.3 if full else 0.8,
                confidence=0.6,
                findings=["full frame" if full else "crop"],
            )

    service = AnalysisService(
        analyzers=[Shot(), ByShape("fft")],
        fusion=WeightedFusionPolicy(),
        artifacts=InMemoryArtifactStore(),
        content_analyzers=[ByShape("fft")],
        enable_probes=False,
    )
    buf = io.BytesIO()
    Image.new("RGB", (200, 200), (90, 90, 90)).save(buf, format="PNG")
    outcome = service.analyze_bytes(buf.getvalue(), "shot.png")
    fft = next(s for s in outcome.signals if s.id == "fft")
    assert fft.score == pytest.approx(0.8)
    assert "[content region] crop" in fft.findings
    assert fft.details["content_region_score"] == pytest.approx(0.8)
