"""Error Level Analysis (JPEG recompression residual)."""

from __future__ import annotations

import io

import cv2
import numpy as np
from PIL import Image

from ai_image_authenticator.application.analyzers.base import BaseAnalyzer
from ai_image_authenticator.domain.models import AnalyzerOutput

ELA_MAX_SIDE = 2048


def _to_png_bytes(arr: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", arr)
    if not ok:
        raise RuntimeError("Failed to encode ELA visualization")
    return buf.tobytes()


def _ela_at_quality(rgb_u8: np.ndarray, quality: int) -> tuple[np.ndarray, float, float, float]:
    pil = Image.fromarray(rgb_u8)
    buf = io.BytesIO()
    pil.save(buf, format="JPEG", quality=quality)
    buf.seek(0)
    recompressed = np.asarray(Image.open(buf).convert("RGB"), dtype=np.int16)
    orig = rgb_u8.astype(np.int16)
    diff = np.abs(orig - recompressed).astype(np.float32)
    mean_res = float(diff.mean())
    max_res = float(diff.max())
    std_res = float(diff.std())
    return diff, mean_res, max_res, std_res


class ErrorLevelAnalysis(BaseAnalyzer):
    id = "ela"
    name = "Error Level Analysis"

    def analyze(self, image: Image.Image, rgb: np.ndarray, raw_bytes: bytes, filename: str) -> AnalyzerOutput:
        rgb_u8 = np.asarray(image.convert("RGB"), dtype=np.uint8)
        # Like the other pixel analyzers, bound the working size: ELA allocates ~20 B/px twice
        h0, w0 = rgb_u8.shape[:2]
        scale = min(1.0, ELA_MAX_SIDE / max(h0, w0))
        if scale < 1.0:
            rgb_u8 = cv2.resize(rgb_u8, (int(w0 * scale), int(h0 * scale)), interpolation=cv2.INTER_AREA)

        # Primary ELA at Q90 + secondary at Q75 for multi-quality agreement
        diff90, mean_res, max_res, std_res = _ela_at_quality(rgb_u8, 90)
        diff75, mean75, _, _ = _ela_at_quality(rgb_u8, 75)
        quality_delta = float(abs(mean_res - mean75))

        ela = np.clip(diff90 * 12.0, 0, 255).astype(np.uint8)
        ela_gray = cv2.cvtColor(ela, cv2.COLOR_RGB2GRAY)

        h, w = ela_gray.shape
        block = 32
        energies = []
        for y in range(0, h - block + 1, block):
            for x in range(0, w - block + 1, block):
                energies.append(float(ela_gray[y : y + block, x : x + block].mean()))
        energies_arr = np.array(energies) if energies else np.array([0.0])
        spatial_cv = float(energies_arr.std() / (energies_arr.mean() + 1e-6))

        # Edge-aware residual: residual concentrated on edges vs flats
        gray = cv2.cvtColor(rgb_u8, cv2.COLOR_RGB2GRAY)
        edges = cv2.Canny(gray, 80, 160)
        edge_mask = edges > 0
        if edge_mask.any() and (~edge_mask).any():
            edge_res = float(diff90.mean(axis=2)[edge_mask].mean())
            flat_res = float(diff90.mean(axis=2)[~edge_mask].mean())
            edge_ratio = float(edge_res / (flat_res + 1e-6))
        else:
            edge_ratio = 1.0

        findings = []
        score = 0.4
        confidence = 0.55

        if mean_res < 1.15 and spatial_cv < 0.32:
            score = 0.74
            confidence = 0.68
            findings.append(
                f"Very low recompression residual (mean={mean_res:.2f}) with uniform ELA — "
                "often seen in generative/smooth imagery"
            )
        elif mean_res < 2.4 and spatial_cv < 0.48:
            score = 0.60
            confidence = 0.58
            findings.append(f"Moderately low ELA residual (mean={mean_res:.2f})")
        elif spatial_cv > 1.15 and max_res > 40:
            score = 0.64
            confidence = 0.62
            findings.append(
                f"Patchy ELA (spatial CV={spatial_cv:.2f}) — possible composite / mixed sources"
            )
        elif mean_res > 4.0 and 0.4 < spatial_cv < 1.0:
            score = 0.26
            confidence = 0.55
            findings.append(
                f"Camera-like residual texture (mean={mean_res:.2f}, CV={spatial_cv:.2f})"
            )
        else:
            score = 0.45
            findings.append(
                f"ELA residual mean={mean_res:.2f}, max={max_res:.1f}, spatial CV={spatial_cv:.2f}"
            )

        # Multi-quality: generative flats stay low across Q75/Q90
        if mean_res < 2.0 and mean75 < 2.8 and quality_delta < 1.2:
            score = min(1.0, score + 0.07)
            confidence = min(0.88, confidence + 0.06)
            findings.append(
                f"Multi-quality ELA stays low (Q90={mean_res:.2f}, Q75={mean75:.2f}, Δ={quality_delta:.2f})"
            )

        if edge_ratio < 1.15 and mean_res < 2.5:
            score = min(1.0, score + 0.05)
            findings.append(
                f"Flat vs edge residual ratio low ({edge_ratio:.2f}) — residual not camera-edge dominated"
            )

        heat = cv2.applyColorMap(ela_gray, cv2.COLORMAP_INFERNO)
        viz = _to_png_bytes(heat)

        return AnalyzerOutput(
            id=self.id,
            name=self.name,
            score=float(np.clip(score, 0, 1)),
            confidence=float(np.clip(confidence, 0, 1)),
            findings=findings,
            visualization=viz,
            details={
                "mean_residual": mean_res,
                "mean_residual_q75": mean75,
                "quality_delta": quality_delta,
                "max_residual": max_res,
                "std_residual": std_res,
                "spatial_cv": spatial_cv,
                "edge_flat_ratio": edge_ratio,
            },
        )
