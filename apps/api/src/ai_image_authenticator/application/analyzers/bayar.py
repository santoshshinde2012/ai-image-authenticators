"""Bayar-style constrained prediction residual (explainable map + score).

Inspired by Bayar & Stamm (constrained convolutional layers for forgery detection):
predict each pixel from its local neighborhood with a fixed high-pass kernel whose
center weight is forced so coefficients sum to zero (prediction-error residual).
Synthetic imagery often shows suppressed or overly regular prediction residuals
compared with camera-captured noise.

This is a classical, CPU-only approximation — not a trained CNN.
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
        raise RuntimeError("Failed to encode Bayar residual visualization")
    return buf.tobytes()


def prediction_residual(gray: np.ndarray) -> np.ndarray:
    """3x3 constrained predictor: neighbors sum to 1, center = -1 (high-pass)."""
    # Bayar-style: peripheral weights equal, center constrained to -sum(neighbors)
    kernel = np.array(
        [
            [1, 1, 1],
            [1, 0, 1],
            [1, 1, 1],
        ],
        dtype=np.float32,
    )
    kernel /= kernel.sum()  # neighbors sum to 1
    kernel[1, 1] = -1.0  # constrained center
    return cv2.filter2D(gray, cv2.CV_32F, kernel)


class BayarPredictionResidual(BaseAnalyzer):
    """id=`bayar` — prediction-error residual energy / regularity."""

    id = "bayar"
    name = "Bayar Prediction Residual"

    def analyze(
        self, image: Image.Image, rgb: np.ndarray, raw_bytes: bytes, filename: str
    ) -> AnalyzerOutput:
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
        max_side = 1024
        h, w = gray.shape
        scale = min(1.0, max_side / max(h, w))
        if scale < 1.0:
            gray = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

        residual = prediction_residual(gray)
        abs_res = np.abs(residual)
        mean_abs = float(abs_res.mean())
        std_abs = float(abs_res.std())
        # Local regularity: coefficient of variation of block energies
        block = 16
        hh, ww = abs_res.shape
        energies = []
        for y in range(0, hh - block + 1, block):
            for x in range(0, ww - block + 1, block):
                energies.append(float(abs_res[y : y + block, x : x + block].mean()))
        energy_arr = np.array(energies, dtype=np.float64) if energies else np.array([0.0])
        energy_cv = float(energy_arr.std() / (energy_arr.mean() + 1e-6))
        # Autocorrelation at lag-1 (synthetic often smoother / more correlated residuals)
        flat = residual.ravel()
        if flat.size > 2:
            lag1 = float(np.corrcoef(flat[:-1], flat[1:])[0, 1])
            if not np.isfinite(lag1):
                lag1 = 0.0
        else:
            lag1 = 0.0

        findings: list[str] = []
        score = 0.4
        confidence = 0.55

        # Very low prediction-error energy → missing sensor / demosaic noise
        if mean_abs < 1.8:
            score = 0.78
            confidence = 0.72
            findings.append(
                f"Very low prediction residual energy (mean|e|={mean_abs:.2f}) — "
                "camera prediction-error noise largely absent"
            )
        elif mean_abs < 4.5:
            score = 0.60
            findings.append(f"Below-typical prediction residual energy (mean|e|={mean_abs:.2f})")
        else:
            score = 0.28
            findings.append(f"Healthy prediction residual energy (mean|e|={mean_abs:.2f})")

        if abs(lag1) > 0.55 and mean_abs < 8:
            score = min(1.0, score + 0.08)
            confidence = min(0.88, confidence + 0.06)
            findings.append(
                f"High residual lag-1 correlation ({lag1:.2f}) — overly smooth prediction errors"
            )

        if energy_cv < 0.35 and mean_abs < 6:
            score = min(1.0, score + 0.07)
            findings.append(
                f"Unusually uniform residual energy (CV={energy_cv:.2f}) across blocks"
            )
        elif energy_cv > 1.6 and mean_abs > 1.0:
            score = min(1.0, score + 0.05)
            findings.append(
                f"Spatially inconsistent residual energy (CV={energy_cv:.2f}) — possible mixed regions"
            )

        if not findings:
            findings.append("No strong Bayar prediction-residual anomalies")

        viz = cv2.normalize(abs_res, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
        heat = cv2.applyColorMap(viz, cv2.COLORMAP_TURBO)

        return AnalyzerOutput(
            id=self.id,
            name=self.name,
            score=float(np.clip(score, 0, 1)),
            confidence=float(np.clip(confidence, 0, 1)),
            findings=findings,
            visualization=_to_png_bytes(heat),
            details={
                "mean_abs_residual": mean_abs,
                "std_abs_residual": std_abs,
                "block_energy_cv": energy_cv,
                "lag1_correlation": lag1,
                "kernel": "bayar_constrained_3x3",
            },
        )
