"""SRM-style rich residual model features (Fridrich & Kodovský lineage).

Computes a compact bank of high-pass residuals used in steganalysis / image forensics
(SRM) and in TRIDENT-style spectral residual paths. We keep a CPU-friendly subset:
first-order and second-order directional residuals + co-occurrence-lite statistics
(mean abs, variance, kurtosis, histogram entropy). Full 34-filter SRM with quantized
co-occurrence matrices is deferred for latency; this still exposes explainable residual maps.
"""

from __future__ import annotations

import cv2
import numpy as np
from PIL import Image

from ai_image_authenticator.application.analyzers.base import BaseAnalyzer
from ai_image_authenticator.application.analyzers.bayar import prediction_residual
from ai_image_authenticator.domain.models import AnalyzerOutput


def _to_png_bytes(arr: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", arr)
    if not ok:
        raise RuntimeError("Failed to encode SRM visualization")
    return buf.tobytes()


def _residual_stats(res: np.ndarray) -> dict[str, float]:
    flat = res.ravel().astype(np.float64)
    abs_f = np.abs(flat)
    mean_abs = float(abs_f.mean())
    var = float(flat.var())
    z = (flat - flat.mean()) / (flat.std() + 1e-6)
    kurt = float(np.mean(z**4) - 3.0)
    # Histogram entropy on clipped residual
    clipped = np.clip(flat, -20, 20)
    hist, _ = np.histogram(clipped, bins=41, range=(-20, 20), density=True)
    hist = hist + 1e-12
    entropy = float(-(hist * np.log(hist)).sum())
    return {
        "mean_abs": mean_abs,
        "variance": var,
        "kurtosis": kurt,
        "hist_entropy": entropy,
    }


class SRMResidualAnalyzer(BaseAnalyzer):
    """id=`srm` — rich high-pass residual bank + residual-map visualization."""

    id = "srm"
    name = "SRM Residuals"

    def analyze(
        self, image: Image.Image, rgb: np.ndarray, raw_bytes: bytes, filename: str
    ) -> AnalyzerOutput:
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
        max_side = 768
        h, w = gray.shape
        scale = min(1.0, max_side / max(h, w))
        if scale < 1.0:
            gray = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

        # First-order directional residuals (SRM-like)
        kx = np.array([[0, 0, 0], [0, -1, 1], [0, 0, 0]], dtype=np.float32)
        ky = np.array([[0, 0, 0], [0, -1, 0], [0, 1, 0]], dtype=np.float32)
        kd1 = np.array([[0, 0, 0], [0, -1, 0], [0, 0, 1]], dtype=np.float32)
        kd2 = np.array([[0, 0, 0], [0, -1, 0], [1, 0, 0]], dtype=np.float32)
        # Second-order
        kxx = np.array([[0, 0, 0], [1, -2, 1], [0, 0, 0]], dtype=np.float32)
        kyy = np.array([[0, 1, 0], [0, -2, 0], [0, 1, 0]], dtype=np.float32)

        residuals = {
            "spam_h": cv2.filter2D(gray, cv2.CV_32F, kx),
            "spam_v": cv2.filter2D(gray, cv2.CV_32F, ky),
            "spam_d1": cv2.filter2D(gray, cv2.CV_32F, kd1),
            "spam_d2": cv2.filter2D(gray, cv2.CV_32F, kd2),
            "second_h": cv2.filter2D(gray, cv2.CV_32F, kxx),
            "second_v": cv2.filter2D(gray, cv2.CV_32F, kyy),
            "bayar": prediction_residual(gray),
        }

        per_filter: dict[str, dict[str, float]] = {}
        mean_abs_vals: list[float] = []
        kurt_vals: list[float] = []
        entropy_vals: list[float] = []
        for name, res in residuals.items():
            st = _residual_stats(res)
            per_filter[name] = st
            mean_abs_vals.append(st["mean_abs"])
            kurt_vals.append(st["kurtosis"])
            entropy_vals.append(st["hist_entropy"])

        mean_abs = float(np.mean(mean_abs_vals))
        mean_kurt = float(np.mean(kurt_vals))
        mean_entropy = float(np.mean(entropy_vals))
        # Cross-filter agreement of residual energy (synthetic often collapses filters)
        energy_cv = float(np.std(mean_abs_vals) / (np.mean(mean_abs_vals) + 1e-6))

        # Composite residual magnitude for viz (max abs across first-order)
        stack = np.stack([np.abs(residuals[k]) for k in ("spam_h", "spam_v", "spam_d1", "spam_d2")], axis=0)
        composite = stack.max(axis=0)

        findings: list[str] = []
        score = 0.4
        confidence = 0.58

        if mean_abs < 2.0:
            score = 0.80
            confidence = 0.74
            findings.append(
                f"SRM residual energy suppressed (mean|r|={mean_abs:.2f}) — "
                "sensor/steganographic noise floor largely missing"
            )
        elif mean_abs < 5.5:
            score = 0.62
            findings.append(f"Reduced SRM residual energy (mean|r|={mean_abs:.2f})")
        else:
            score = 0.26
            findings.append(f"Present SRM residual energy (mean|r|={mean_abs:.2f})")

        # Overly platykurtic / low-entropy residuals → quantized synthetic textures
        if mean_kurt < -0.3 and mean_abs < 8:
            score = min(1.0, score + 0.06)
            findings.append(f"Platykurtic residual distribution (kurt={mean_kurt:.2f})")
        if mean_entropy < 2.4 and mean_abs < 8:
            score = min(1.0, score + 0.07)
            confidence = min(0.88, confidence + 0.05)
            findings.append(f"Low residual histogram entropy ({mean_entropy:.2f}) — quantized noise")

        if energy_cv < 0.12 and mean_abs < 7:
            score = min(1.0, score + 0.06)
            findings.append(
                f"Filters agree on low energy (cross-filter CV={energy_cv:.2f}) — TRIDENT-like residual collapse"
            )

        bayar_ma = per_filter["bayar"]["mean_abs"]
        if bayar_ma < 2.2 and mean_abs < 6:
            score = min(1.0, score + 0.05)
            findings.append(f"Bayar prediction residual also suppressed (mean|e|={bayar_ma:.2f})")

        if not findings:
            findings.append("No strong SRM residual anomalies")

        viz = cv2.normalize(composite, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
        heat = cv2.applyColorMap(viz, cv2.COLORMAP_INFERNO)

        return AnalyzerOutput(
            id=self.id,
            name=self.name,
            score=float(np.clip(score, 0, 1)),
            confidence=float(np.clip(confidence, 0, 1)),
            findings=findings,
            visualization=_to_png_bytes(heat),
            details={
                "mean_abs_residual": mean_abs,
                "mean_kurtosis": mean_kurt,
                "mean_hist_entropy": mean_entropy,
                "cross_filter_energy_cv": energy_cv,
                "per_filter": per_filter,
                "filter_bank": list(residuals.keys()),
                "citation": "Fridrich & Kodovsky SRM; TRIDENT spectral residual path",
            },
        )
