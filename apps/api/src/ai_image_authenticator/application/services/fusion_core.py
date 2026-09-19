"""Shared fusion constants and helpers (kept separate for maintainability)."""

from __future__ import annotations

from ai_image_authenticator.application.services.weights import DEFAULT_WEIGHTS, WEIGHTS
from ai_image_authenticator.domain.verdict import Verdict

__all__ = [
    "DEFAULT_WEIGHTS",
    "WEIGHTS",
    "PROVENANCE_CONTRACT_IDS",
    "PIXEL_FORENSIC_IDS",
    "LIMITATIONS",
    "_summary",
    "_normalize_score",
    "fusion_math",
]

PROVENANCE_CONTRACT_IDS = frozenset({"provenance", "labels"})
PIXEL_FORENSIC_IDS = frozenset(
    {"ela", "fft", "dct", "noise", "texture", "metadata", "srm", "bayar", "local_corr"}
)

LIMITATIONS = [
    "No detector is perfect; generators and post-processing evolve quickly.",
    "Classical forensics generalize unevenly across Midjourney, SD, Firefly, DALL·E, etc.",
    "Screenshots and heavy compression can mask or mimic AI cues.",
    "Camera EXIF can be stripped or spoofed; absence ≠ proof of AI.",
    "OCR can miss stylized badges; lack of a visible label does not prove authenticity.",
    "C2PA/Content Credentials are often stripped by platform re-encode, download, or screenshot — "
    "absence is expected and is not proof of authenticity.",
    "C2PA path uses marker/assertion extraction + optional c2pa-python Reader validation_state; "
    "trust-anchor fetch is optional and CI stays offline — not full courtroom crypto validation.",
    "Industry 2026 dual-layer provenance (C2PA metadata + SynthID-class watermarks) is complementary; "
    "this tool inspects the C2PA/OCR/forensics side and does not decode proprietary SynthID keys.",
    "X's Made with AI appears C2PA-oriented at upload (caBX / digitalSourceType), but independent "
    "tests (e.g. Roboin) suggest undisclosed criteria may also apply — do not overclaim C2PA-only.",
    "SRM/Bayar/local-correlation features are compact classical approximations, not full SRM "
    "co-occurrence CNNs or trained NPR detectors.",
    "This tool is not a platform upload pipeline (e.g. X's Made with AI gate).",
    "This v1 uses an offline classical ensemble + OCR + C2PA detection (optional deep model is Phase 2).",
    "No universal detector: generator/domain shift and transformation bias remain open; "
    "challenge_flags + failure_modes mark laundering, dual-layer awareness, and signal conflicts rather than claiming solved accuracy.",
]


def _summary(
    verdict: Verdict,
    prob: float,
    screenshot: bool,
    top_findings: list[str],
    evidence_paths: list[str],
) -> str:
    labels = {
        Verdict.REAL: "Likely a real photograph / natural capture",
        Verdict.INCONCLUSIVE: "Inconclusive — mixed or weak forensic signals",
        Verdict.LIKELY_AI: "Likely AI-generated or heavily synthetic",
        Verdict.AI_GENERATED: "Strong indicators of AI / synthetic imagery",
    }
    base = f"{labels[verdict]} (ensemble AI probability {prob:.0%})."
    if evidence_paths:
        base += " Evidence paths: " + ", ".join(evidence_paths) + "."
    if screenshot:
        base += (
            " Image appears screenshot-like; embedded content may still be AI "
            "even if UI chrome is real."
        )
    if top_findings:
        base += " Key signals: " + "; ".join(top_findings[:3]) + "."
    return base


def _normalize_score(score: float, confidence: float) -> float:
    """Shrink extreme scores when analyzer confidence is low (toward 0.5)."""
    c = float(max(0.0, min(1.0, confidence)))
    s = float(max(0.0, min(1.0, score)))
    return 0.5 + (s - 0.5) * (0.35 + 0.65 * c)


def fusion_math(scores: dict[str, float], weights: dict[str, float] | None = None) -> float:
    """Pure fusion math helper for unit tests (no confidence normalization)."""
    w = weights or DEFAULT_WEIGHTS
    numer = 0.0
    denom = 0.0
    for k, weight in w.items():
        if k in scores:
            numer += scores[k] * weight
            denom += weight
    return numer / denom if denom else 0.5
