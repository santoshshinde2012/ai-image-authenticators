"""Texture / gradient / local entropy analysis."""

from __future__ import annotations

import cv2
import numpy as np
from PIL import Image

from ai_image_authenticator.application.analyzers.base import BaseAnalyzer
from ai_image_authenticator.domain.models import AnalyzerOutput


def _local_entropy(gray: np.ndarray, ksize: int = 9) -> float:
    h, w = gray.shape
    ents = []
    step = max(8, ksize)
    for y in range(0, h - ksize, step):
        for x in range(0, w - ksize, step):
            tile = gray[y : y + ksize, x : x + ksize]
            hist = cv2.calcHist([tile], [0], None, [32], [0, 256]).ravel()
            p = hist / (hist.sum() + 1e-12)
            p = p[p > 0]
            ents.append(float(-(p * np.log2(p)).sum()))
    return float(np.mean(ents)) if ents else 0.0


def _glcm_contrast_homogeneity(gray: np.ndarray) -> tuple[float, float]:
    g = cv2.resize(gray, (128, 128), interpolation=cv2.INTER_AREA)
    q = (g // 64).astype(np.int32)
    levels = 4
    glcm = np.zeros((levels, levels), dtype=np.float64)
    a = q[:, :-1].ravel()
    b = q[:, 1:].ravel()
    for i, j in zip(a, b, strict=False):
        glcm[i, j] += 1
    s = glcm.sum()
    if s < 1:
        return 0.0, 1.0
    glcm /= s
    contrast = 0.0
    homogeneity = 0.0
    for i in range(levels):
        for j in range(levels):
            p = glcm[i, j]
            contrast += p * (i - j) ** 2
            homogeneity += p / (1.0 + abs(i - j))
    return float(contrast), float(homogeneity)


class TextureGradient(BaseAnalyzer):
    id = "texture"
    name = "Texture & Gradient"

    def analyze(self, image: Image.Image, rgb: np.ndarray, raw_bytes: bytes, filename: str) -> AnalyzerOutput:
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        max_side = 1024
        h, w = gray.shape
        scale = min(1.0, max_side / max(h, w))
        if scale < 1.0:
            gray = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

        gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        mag = cv2.magnitude(gx, gy)
        mean_grad = float(mag.mean())
        soft_frac = float(np.mean(mag < 8.0))
        hist, _ = np.histogram(mag.ravel(), bins=32, range=(0, 200), density=True)
        peakiness = float(hist.max())
        entropy = _local_entropy(gray)
        contrast, homogeneity = _glcm_contrast_homogeneity(gray)
        lap_var = float(cv2.Laplacian(gray, cv2.CV_32F).var())

        g = gray.astype(np.int16)
        diffs = []
        for dy, dx in [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]:
            diffs.append(
                np.abs(
                    g[1:-1, 1:-1]
                    - g[1 + dy : g.shape[0] - 1 + dy, 1 + dx : g.shape[1] - 1 + dx]
                )
            )
        neighbor_mean = float(np.mean(diffs))

        findings = []
        score = 0.4
        confidence = 0.55

        if mean_grad < 11.5 and soft_frac > 0.55:
            score = 0.74
            confidence = 0.70
            findings.append(
                f"Over-smooth gradients (mean={mean_grad:.1f}, soft={soft_frac:.0%}) atypical of camera photos"
            )
        elif mean_grad < 17.5 and soft_frac > 0.4:
            score = 0.60
            findings.append(f"Soft texture profile (mean grad={mean_grad:.1f})")
        elif mean_grad > 28:
            score = 0.24
            findings.append(f"Strong natural-like gradient energy (mean={mean_grad:.1f})")
        else:
            score = 0.42
            findings.append(f"Moderate texture (mean grad={mean_grad:.1f}, entropy={entropy:.2f})")

        if entropy < 3.15:
            score = min(1.0, score + 0.1)
            findings.append(f"Low local entropy ({entropy:.2f}) suggests homogenized regions")
        elif entropy > 5.0:
            score = max(0.0, score - 0.08)
            findings.append(f"High local entropy ({entropy:.2f}) favors photographic detail")

        if neighbor_mean < 3.8:
            score = min(1.0, score + 0.08)
            findings.append("Neighbor pixel differences unusually small (painterly smoothness)")

        if homogeneity > 0.72 and contrast < 0.55:
            score = min(1.0, score + 0.08)
            confidence = min(0.88, confidence + 0.06)
            findings.append(
                f"High GLCM homogeneity ({homogeneity:.2f}) / low contrast ({contrast:.2f})"
            )
        elif contrast > 1.4:
            score = max(0.0, score - 0.06)
            findings.append(f"GLCM contrast ({contrast:.2f}) favors natural texture variation")

        if lap_var < 30 and soft_frac > 0.45:
            score = min(1.0, score + 0.06)
            findings.append(f"Low Laplacian texture energy ({lap_var:.1f})")

        return AnalyzerOutput(
            id=self.id, name=self.name,
            score=float(np.clip(score, 0, 1)), confidence=float(np.clip(confidence, 0, 1)),
            findings=findings,
            details={
                "mean_gradient": mean_grad, "soft_fraction": soft_frac,
                "local_entropy": entropy, "neighbor_mean_diff": neighbor_mean,
                "grad_peakiness": peakiness, "glcm_contrast": contrast,
                "glcm_homogeneity": homogeneity, "laplacian_variance": lap_var,
            },
        )
