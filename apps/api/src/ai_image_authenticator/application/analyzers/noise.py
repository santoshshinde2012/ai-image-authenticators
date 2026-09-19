"""Wavelet / high-pass noise residual analysis."""

from __future__ import annotations

import cv2
import numpy as np
import pywt
from PIL import Image

from ai_image_authenticator.application.analyzers.base import BaseAnalyzer
from ai_image_authenticator.domain.models import AnalyzerOutput


def _to_png_bytes(arr: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", arr)
    if not ok:
        raise RuntimeError("Failed to encode noise visualization")
    return buf.tobytes()


class NoiseResidual(BaseAnalyzer):
    id = "noise"
    name = "Noise Residual"

    def analyze(self, image: Image.Image, rgb: np.ndarray, raw_bytes: bytes, filename: str) -> AnalyzerOutput:
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
        max_side = 1024
        h, w = gray.shape
        scale = min(1.0, max_side / max(h, w))
        if scale < 1.0:
            gray = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
            rgb_s = cv2.resize(rgb, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        else:
            rgb_s = rgb

        coeffs = pywt.dwt2(gray, "db1")
        cA, (cH, cV, cD) = coeffs
        residual = pywt.idwt2((np.zeros_like(cA), (cH, cV, cD)), "db1")
        residual = residual[: gray.shape[0], : gray.shape[1]]

        abs_res = np.abs(residual)
        block = 16
        hh, ww = abs_res.shape
        var_map = np.zeros((hh // block, ww // block), dtype=np.float32)
        for yi, y in enumerate(range(0, hh - block + 1, block)):
            for xi, x in enumerate(range(0, ww - block + 1, block)):
                tile = residual[y : y + block, x : x + block]
                var_map[yi, xi] = float(tile.var())

        mean_var = float(var_map.mean()) if var_map.size else 0.0
        std_var = float(var_map.std()) if var_map.size else 0.0
        cv_var = float(std_var / (mean_var + 1e-6))
        flat_frac = float(np.mean(var_map < np.percentile(var_map, 20) * 0.5)) if var_map.size else 0.0

        lap_var = float(cv2.Laplacian(gray, cv2.CV_32F).var())

        channel_corr = 0.0
        try:
            chans = [rgb_s[:, :, i].astype(np.float32) for i in range(3)]
            hp = []
            for ch in chans:
                blur = cv2.GaussianBlur(ch, (5, 5), 0)
                hp.append((ch - blur).ravel())
            corrs = []
            for i, j in ((0, 1), (0, 2), (1, 2)):
                a, b = hp[i], hp[j]
                if a.std() < 1e-6 or b.std() < 1e-6:
                    continue
                corrs.append(float(np.corrcoef(a, b)[0, 1]))
            if corrs:
                channel_corr = float(np.mean(np.abs(corrs)))
        except Exception:
            channel_corr = 0.0

        findings = []
        score = 0.4
        confidence = 0.55

        if mean_var < 2.3:
            score = 0.76
            confidence = 0.72
            findings.append(
                f"Very low wavelet residual energy (mean var={mean_var:.2f}) — sensor noise largely absent"
            )
        elif mean_var < 7.5:
            score = 0.60
            findings.append(f"Below-typical noise energy (mean var={mean_var:.2f})")
        else:
            score = 0.26
            findings.append(f"Present residual noise (mean var={mean_var:.2f})")

        if lap_var < 25 and mean_var < 10:
            score = min(1.0, score + 0.08)
            findings.append(f"Low Laplacian variance ({lap_var:.1f}) — weak high-frequency grain")
        elif lap_var > 120:
            score = max(0.0, score - 0.06)
            findings.append(f"Healthy Laplacian energy ({lap_var:.1f})")

        if channel_corr > 0.92 and mean_var < 12:
            score = min(1.0, score + 0.09)
            confidence = min(0.88, confidence + 0.08)
            findings.append(
                f"High cross-channel residual correlation ({channel_corr:.2f}) — synthetic smoothness"
            )

        if cv_var > 1.75 and mean_var > 1.0:
            score = min(1.0, score + 0.1)
            findings.append(
                f"Inconsistent block noise (CV={cv_var:.2f}) — possible mixed regions / inpainting"
            )
        if flat_frac > 0.33 and mean_var < 12:
            score = min(1.0, score + 0.08)
            findings.append(f"Large unusually flat residual regions ({flat_frac:.0%} of blocks)")

        viz_gray = cv2.normalize(abs_res, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
        heat = cv2.applyColorMap(viz_gray, cv2.COLORMAP_TURBO)
        viz = _to_png_bytes(heat)

        return AnalyzerOutput(
            id=self.id, name=self.name,
            score=float(np.clip(score, 0, 1)), confidence=float(np.clip(confidence, 0, 1)),
            findings=findings, visualization=viz,
            details={
                "mean_block_variance": mean_var, "variance_cv": cv_var,
                "flat_block_fraction": flat_frac, "laplacian_variance": lap_var,
                "cross_channel_corr": channel_corr,
            },
        )
