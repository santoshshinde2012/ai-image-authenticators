"""Local correlation / upsampling-residue cues (NPR / ForenAgent-style).

Synthetic generators and neural upsamplers leave measurable structure in:
  1) Neighbor-pixel correlation anisotropy (checker / grid preferences)
  2) Null-transform upsampling residue: downsample → upsample → residual (NPR-like)

CPU-only; produces an explainable residue heatmap.
"""

from __future__ import annotations

import cv2
import numpy as np
from PIL import Image

from ai_image_authenticator.application.analyzers.base import BaseAnalyzer
from ai_image_authenticator.domain.models import AnalyzerOutput


def _to_png_bytes(arr: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", arr)
    if not ok:
        raise RuntimeError("Failed to encode local-correlation visualization")
    return buf.tobytes()


def _neighbor_corr(gray: np.ndarray) -> dict[str, float]:
    """Pearson correlation with 1-px shifts (H/V/D)."""
    a = gray[1:-1, 1:-1].ravel()
    shifts = {
        "h": gray[1:-1, 2:].ravel(),
        "v": gray[2:, 1:-1].ravel(),
        "d": gray[2:, 2:].ravel(),
        "ad": gray[2:, :-2].ravel() if gray.shape[1] > 2 else gray[2:, 1:-1].ravel(),
    }
    out: dict[str, float] = {}
    for k, b in shifts.items():
        n = min(a.size, b.size)
        aa, bb = a[:n], b[:n]
        if aa.std() < 1e-6 or bb.std() < 1e-6:
            out[k] = 0.0
        else:
            out[k] = float(np.corrcoef(aa, bb)[0, 1])
    vals = list(out.values())
    out["mean"] = float(np.mean(vals))
    out["anisotropy"] = float(np.std(vals))
    return out


def _npr_residue(gray: np.ndarray, factor: int = 2) -> tuple[np.ndarray, float]:
    """Null-transform upsampling residue (NPR-style)."""
    h, w = gray.shape
    # Downsample with area, upsample with cubic (common generative upsampler family)
    small = cv2.resize(gray, (max(1, w // factor), max(1, h // factor)), interpolation=cv2.INTER_AREA)
    up = cv2.resize(small, (w, h), interpolation=cv2.INTER_CUBIC)
    residue = gray - up
    energy = float(np.mean(np.abs(residue)))
    return residue, energy


class LocalCorrelationAnalyzer(BaseAnalyzer):
    """id=`local_corr` — neighbor correlation + NPR upsampling residue."""

    id = "local_corr"
    name = "Local Correlation / Upsampling Residue"

    def analyze(
        self, image: Image.Image, rgb: np.ndarray, raw_bytes: bytes, filename: str
    ) -> AnalyzerOutput:
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
        max_side = 1024
        h, w = gray.shape
        scale = min(1.0, max_side / max(h, w))
        if scale < 1.0:
            gray = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

        corr = _neighbor_corr(gray)
        residue, npr_energy = _npr_residue(gray, factor=2)
        residue4, npr_energy4 = _npr_residue(gray, factor=4)

        # Checkerboard preference: |h-v| and diagonal vs axial
        hv_gap = abs(corr["h"] - corr["v"])
        diag_mean = 0.5 * (corr["d"] + corr["ad"])
        axial_mean = 0.5 * (corr["h"] + corr["v"])
        diag_bias = float(diag_mean - axial_mean)

        # Periodic residue energy ratio (FFT of |residue| peaks)
        abs_res = np.abs(residue)
        f = np.fft.fftshift(np.fft.fft2(abs_res))
        mag = np.abs(f)
        cy, cx = np.array(mag.shape) // 2
        # Exclude DC neighborhood
        mag[cy - 2 : cy + 3, cx - 2 : cx + 3] = 0
        peak = float(mag.max() / (mag.mean() + 1e-6))

        findings: list[str] = []
        score = 0.4
        confidence = 0.55

        # Very high neighbor correlation + low NPR energy → oversmoothed synthetic
        if corr["mean"] > 0.985 and npr_energy < 3.5:
            score = 0.76
            confidence = 0.7
            findings.append(
                f"Extremely high local correlation ({corr['mean']:.3f}) with weak NPR residue "
                f"({npr_energy:.2f}) — generative smoothness / upsampler footprint"
            )
        elif corr["mean"] > 0.97 and npr_energy < 6:
            score = 0.62
            findings.append(
                f"Elevated local correlation ({corr['mean']:.3f}); NPR energy={npr_energy:.2f}"
            )
        else:
            score = 0.32
            findings.append(
                f"Local correlation mean={corr['mean']:.3f}; NPR energy={npr_energy:.2f}"
            )

        if hv_gap > 0.04 and corr["anisotropy"] > 0.03:
            score = min(1.0, score + 0.07)
            confidence = min(0.88, confidence + 0.05)
            findings.append(
                f"H/V correlation anisotropy (Δ={hv_gap:.3f}) — directional synthetic structure"
            )

        if abs(diag_bias) > 0.03 and peak > 8:
            score = min(1.0, score + 0.08)
            findings.append(
                f"Diagonal correlation bias ({diag_bias:.3f}) with periodic NPR peaks "
                f"(peak/mean={peak:.1f}) — upsampling lattice cue"
            )
        elif peak > 12:
            score = min(1.0, score + 0.06)
            findings.append(f"Strong periodic structure in NPR residue (peak/mean={peak:.1f})")

        # Factor-4 residue much larger than factor-2 suggests multi-stage upsampling
        if npr_energy > 1e-3 and (npr_energy4 / (npr_energy + 1e-6)) > 2.2:
            score = min(1.0, score + 0.05)
            findings.append(
                f"Scale-dependent NPR residue (×4/×2={npr_energy4 / (npr_energy + 1e-6):.2f})"
            )

        if not findings:
            findings.append("No strong local-correlation / upsampling-residue cues")

        viz = cv2.normalize(abs_res, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
        heat = cv2.applyColorMap(viz, cv2.COLORMAP_VIRIDIS)

        return AnalyzerOutput(
            id=self.id,
            name=self.name,
            score=float(np.clip(score, 0, 1)),
            confidence=float(np.clip(confidence, 0, 1)),
            findings=findings,
            visualization=_to_png_bytes(heat),
            details={
                "neighbor_corr": corr,
                "npr_energy_x2": npr_energy,
                "npr_energy_x4": npr_energy4,
                "hv_gap": hv_gap,
                "diag_bias": diag_bias,
                "npr_spectral_peak_ratio": peak,
                "citation": "NPR / ForenAgent local-correlation upsampling cues",
            },
        )
