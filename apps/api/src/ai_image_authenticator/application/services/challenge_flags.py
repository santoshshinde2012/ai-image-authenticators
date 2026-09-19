"""Research-challenge awareness helpers for fusion (laundering + signal conflict).

Maps documented challenges → auditable challenge_flags + human failure_modes
without inventing benchmark numbers. See docs/research-challenges.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ai_image_authenticator.domain.models import AnalyzerOutput

LAUNDERING_SENSITIVE_IDS = frozenset({"fft", "srm", "bayar", "local_corr", "dct"})
CONFIDENCE_FLOOR = 0.12
LAUNDERING_TRIGGER = 0.45


def spectral_weight_scale(laundering: float) -> float:
    """Weight multiplier for laundering-sensitive analyzers (1.0 below the trigger).

    Single definition shared by weight accumulation and the audit text, so the dampening
    reported in fusion_reasons is the dampening that was applied.
    """
    if laundering < LAUNDERING_TRIGGER:
        return 1.0
    return max(0.35, 1.0 - 0.55 * laundering)

STATIC_FAILURE_MODES: tuple[str, ...] = (
    "No universal detector: unseen generators and post-processing can evade classical cues.",
    "Proprietary SynthID-class watermarks are not decoded without provider keys.",
    "Classical SRM/FFT/Bayar witnesses weaken under heavy re-encode and modern generators.",
)

FLAG_FAILURE_MODES: dict[str, str] = {
    "compression_laundering": (
        "Compression/screenshot laundering detected — spectral/SRM weights dampened."
    ),
    "laundering_probe": (
        "Controlled JPEG Q=75 probe ran; forensic lean may have shifted under recompression."
    ),
    "generator_shift_uncertainty": (
        "Mild degradation probe disagrees with clean forensic lean — generator/domain shift risk."
    ),
    "signal_disagreement": "Signals disagree across provenance vs pixels and/or EXIF vs forensics.",
    "provenance_vs_pixels_conflict": (
        "OCR/C2PA lean AI while classical pixels lean real — prefer calibrated uncertainty."
    ),
    "possible_overprocessed_camera_photo": (
        "Camera EXIF present with strong AI-leaning forensics — edit, spoof, or mixed capture."
    ),
    "dual_layer_provenance_hint": (
        "C2PA soft-binding/watermarked assertion hints at a dual-layer watermark we cannot verify."
    ),
    "synthid_layer_not_verified": (
        "SynthID (or equivalent) layer asserted or implied but not cryptographically verified."
    ),
    "transform_bias_risk": (
        "High laundering raises transformation/dataset-bias risk — avoid over-trusting spectral cues."
    ),
    "frequency_srm_brittleness": (
        "Frequency/SRM path treated as witness only; dampened when laundering is elevated."
    ),
}


@dataclass
class ChallengeAssessment:
    flags: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    failure_modes: list[str] = field(default_factory=list)
    laundering_score: float = 0.0
    spectral_weight_scale: float = 1.0
    confidence_scale: float = 1.0
    inconclusive_pull: float = 0.0


def _f(details: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        return float(details.get(key, default) or default)
    except (TypeError, ValueError):
        return default


def estimate_compression_laundering(by_id: dict[str, AnalyzerOutput]) -> tuple[float, list[str]]:
    notes: list[str] = []
    score = 0.0
    ela = by_id.get("ela")
    dct = by_id.get("dct")
    shot = by_id.get("screenshot")
    prov = by_id.get("provenance")
    probes = by_id.get("_probes")
    if ela:
        d = ela.details or {}
        mean_res = _f(d, "mean_residual")
        spatial_cv = _f(d, "spatial_cv")
        quality_delta = _f(d, "quality_delta")
        if mean_res >= 3.5 and spatial_cv >= 0.85:
            score += 0.35
            notes.append(f"ELA high residual+patchiness (mean={mean_res:.2f}, CV={spatial_cv:.2f})")
        elif mean_res >= 2.5 and quality_delta >= 1.5:
            score += 0.22
            notes.append(f"ELA multi-quality delta suggests recompress (Δ={quality_delta:.2f})")
    if dct:
        d = dct.details or {}
        periodicity = _f(d, "ac_periodicity")
        if periodicity >= 0.35:
            score += 0.35
            notes.append(f"DCT 8x8 block periodicity ({periodicity:.2f}) — weak recompression cue")
        elif periodicity >= 0.22:
            score += 0.18
            notes.append(f"DCT mild periodicity ({periodicity:.2f})")
    screenshot = bool(shot and (shot.details or {}).get("is_screenshot"))
    manifest = bool(prov and (prov.details or {}).get("manifest_present"))
    if screenshot:
        score += 0.25
        notes.append("screenshot-like capture (platform re-encode / C2PA strip common)")
    if screenshot and not manifest:
        score += 0.15
        notes.append("screenshot without C2PA markers — provenance stripped path")
    if probes and (probes.details or {}).get("laundering_probe"):
        d = probes.details or {}
        delta = d.get("delta_q75")
        if delta is not None and abs(float(delta)) >= 0.08:
            score += 0.18
            notes.append(f"laundering_probe Q=75 mean drift Δ={float(delta):+.3f}")
        elif d.get("probe_disagrees_q75"):
            score += 0.12
            notes.append("laundering_probe disagrees with clean forensic lean")
    return float(min(1.0, score)), notes


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def build_failure_modes(flags: list[str]) -> list[str]:
    modes = list(STATIC_FAILURE_MODES)
    for flag in flags:
        msg = FLAG_FAILURE_MODES.get(flag)
        if msg:
            modes.append(msg)
    return _dedupe(modes)


def assess_challenges(
    by_id: dict[str, AnalyzerOutput],
    *,
    provenance_ai: bool,
    visible_ai_label: bool,
    mean_forensic: float | None,
    lean_ai: int,
    lean_real: int,
    forensic_count: int,
) -> ChallengeAssessment:
    out = ChallengeAssessment()
    laundering, laun_notes = estimate_compression_laundering(by_id)
    out.laundering_score = laundering
    if laundering >= LAUNDERING_TRIGGER:
        out.flags.append("compression_laundering")
        out.spectral_weight_scale = spectral_weight_scale(laundering)
        out.confidence_scale *= max(0.55, 1.0 - 0.35 * laundering)
        detail = "; ".join(laun_notes[:3]) if laun_notes else f"score={laundering:.2f}"
        out.reasons.append(
            f"challenge: compression_laundering (score={laundering:.2f}); "
            f"dampening fft/srm/bayar/local_corr/dct weights ×{out.spectral_weight_scale:.2f} — {detail}"
        )
        out.flags.append("frequency_srm_brittleness")
        out.reasons.append(
            "challenge: frequency_srm_brittleness — FFT/SRM/Bayar kept as witnesses; "
            "spectral weights dampened under laundering"
        )
        out.flags.append("transform_bias_risk")
        out.reasons.append(
            "challenge: transform_bias_risk — high laundering elevates transformation/dataset-bias risk"
        )
    probes = by_id.get("_probes")
    if probes and (probes.details or {}).get("laundering_probe"):
        out.flags.append("laundering_probe")
        d = probes.details or {}
        delta = d.get("delta_q75")
        delta_s = f"Δ={float(delta):+.3f}" if delta is not None else "ran"
        out.reasons.append(
            f"challenge: laundering_probe — controlled JPEG Q=75 pass ({delta_s}); "
            "surfaced in fusion_reasons for audit"
        )
        if d.get("generator_shift_uncertainty") or d.get("probe_disagrees_q85") or d.get(
            "probe_disagrees_q75"
        ):
            out.flags.append("generator_shift_uncertainty")
            out.confidence_scale *= 0.85
            out.inconclusive_pull = max(out.inconclusive_pull, 0.15)
            out.reasons.append(
                "challenge: generator_shift_uncertainty — degradation probe disagrees with clean "
                "forensic lean (TRIDENT-style curriculum lite); reducing confidence"
            )
    prov = by_id.get("provenance")
    if prov:
        pd = prov.details or {}
        soft = bool(pd.get("soft_binding_hint"))
        actions = [str(a).lower() for a in (pd.get("action_labels") or [])]
        watermarked = soft or any(
            "watermarked" in a or "softbinding" in a.replace("_", "") for a in actions
        )
        raw_markers = pd.get("raw_markers") or {}
        if isinstance(raw_markers, dict) and raw_markers.get("has_soft_binding_hint"):
            watermarked = True
        if watermarked or soft:
            out.flags.append("dual_layer_provenance_hint")
            out.flags.append("synthid_layer_not_verified")
            out.reasons.append(
                "challenge: dual_layer_provenance_hint — C2PA mentions watermarked/soft-binding "
                "assertions; synthid_layer_not_verified (no provider keys; awareness only)"
            )
    meta = by_id.get("metadata")
    has_camera = bool(meta and (meta.details or {}).get("has_camera"))
    forensic_strong_ai = (mean_forensic is not None and mean_forensic >= 0.62) or lean_ai >= 4
    forensic_strong_real = (mean_forensic is not None and mean_forensic <= 0.35) or (
        lean_real >= max(3, forensic_count // 2) if forensic_count else False
    )
    provenance_strong_ai = provenance_ai or visible_ai_label
    if provenance_strong_ai and forensic_strong_real and forensic_count >= 4:
        out.flags.append("provenance_vs_pixels_conflict")
        out.flags.append("signal_disagreement")
        # No inconclusive pull here: this flag requires a badge or C2PA claim, and the
        # calibrator never pulls against those floors. Confidence carries the conflict.
        out.confidence_scale *= 0.72
        out.reasons.append(
            "challenge: provenance_vs_pixels_conflict — OCR/C2PA lean AI while classical "
            "pixels lean real; reducing confidence (the badge/C2PA probability floor is kept)"
        )
    if has_camera and forensic_strong_ai and not provenance_strong_ai:
        out.flags.append("possible_overprocessed_camera_photo")
        if "signal_disagreement" not in out.flags:
            out.flags.append("signal_disagreement")
        out.confidence_scale *= 0.78
        out.inconclusive_pull = max(out.inconclusive_pull, 0.18)
        out.reasons.append(
            "challenge: possible_overprocessed_camera_photo — camera EXIF present with "
            "strong AI-leaning forensics; could be heavy edit, spoofed EXIF, or generator "
            "with injected tags — reducing confidence"
        )
    elif has_camera and provenance_strong_ai and forensic_strong_ai:
        if "signal_disagreement" not in out.flags:
            out.flags.append("signal_disagreement")
        out.confidence_scale *= 0.88
        out.reasons.append(
            "challenge: signal_disagreement — camera EXIF alongside generative provenance/"
            "forensics; EXIF may be spoofed or photo heavily post-processed"
        )
    out.flags = _dedupe(out.flags)
    out.failure_modes = build_failure_modes(out.flags)
    return out
