"""DCT / JPEG coefficient statistics (Benford-like AC analysis)."""

from __future__ import annotations

import io

import cv2
import numpy as np
from PIL import Image
from scipy.fftpack import dct

from ai_image_authenticator.application.analyzers.base import BaseAnalyzer
from ai_image_authenticator.domain.models import AnalyzerOutput


def _block_dct_ac(gray: np.ndarray, block: int = 8) -> np.ndarray:
    h, w = gray.shape
    h8, w8 = h - h % block, w - w % block
    gray = gray[:h8, :w8].astype(np.float32)
    coeffs = []
    for y in range(0, h8, block):
        for x in range(0, w8, block):
            tile = gray[y : y + block, x : x + block]
            c = dct(dct(tile.T, norm="ortho").T, norm="ortho")
            ac = c.flatten()[1:]
            coeffs.append(ac)
    if not coeffs:
        return np.array([])
    return np.concatenate(coeffs)


def _grid_aligned_crop(gray: np.ndarray, max_side: int, block: int = 8) -> np.ndarray:
    """Central crop of at most ``max_side`` px whose origin stays on the ``block`` grid."""
    h, w = gray.shape
    ch = min(h, max_side) // block * block
    cw = min(w, max_side) // block * block
    y0 = (h - ch) // 2 // block * block
    x0 = (w - cw) // 2 // block * block
    return gray[y0 : y0 + ch, x0 : x0 + cw]


def _first_digit_hist(values: np.ndarray) -> np.ndarray:
    vals = np.abs(values)
    vals = vals[vals > 1e-6]
    if vals.size == 0:
        return np.ones(9) / 9.0
    exp = np.floor(np.log10(vals))
    mantissa = vals / (10**exp)
    digits = np.clip(mantissa.astype(int), 1, 9)
    hist = np.bincount(digits, minlength=10)[1:10].astype(np.float64)
    hist /= hist.sum() + 1e-12
    return hist


def _benford() -> np.ndarray:
    d = np.arange(1, 10)
    return np.log10(1 + 1 / d)


def _ac_periodicity(ac: np.ndarray) -> float:
    vals = np.abs(ac)
    vals = vals[vals < 40]
    if vals.size < 200:
        return 0.0
    hist, _ = np.histogram(vals, bins=80, range=(0, 40), density=True)
    hist = hist - hist.mean()
    if hist.std() < 1e-9:
        return 0.0
    acf = np.correlate(hist, hist, mode="full")[len(hist) - 1 :]
    acf = acf / (acf[0] + 1e-12)
    return float(np.max(acf[2:7])) if len(acf) > 7 else 0.0


class DCTJpegStats(BaseAnalyzer):
    id = "dct"
    name = "DCT / JPEG Statistics"

    def analyze(self, image: Image.Image, rgb: np.ndarray, raw_bytes: bytes, filename: str) -> AnalyzerOutput:
        fmt = (image.format or "").upper()
        via_jpeg = fmt != "JPEG"
        if via_jpeg:
            gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
            max_side = 768
            h, w = gray.shape
            scale = min(1.0, max_side / max(h, w))
            if scale < 1.0:
                gray = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
            # The controlled JPEG pass happens after resizing, so its 8x8 grid is aligned
            buf = io.BytesIO()
            Image.fromarray(cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)).save(buf, format="JPEG", quality=92)
            buf.seek(0)
            gray = np.asarray(Image.open(buf).convert("L"), dtype=np.uint8)
        else:
            # Never resample a JPEG before the block DCT: resizing moves pixels off the encoder's
            # 8x8 lattice and fabricates periodicity. Decode the stored orientation and crop on
            # the grid instead.
            try:
                gray = np.asarray(Image.open(io.BytesIO(raw_bytes)).convert("L"), dtype=np.uint8)
            except Exception:
                gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
            gray = _grid_aligned_crop(gray, max_side=1024)

        ac = _block_dct_ac(gray)
        findings = []
        if ac.size < 100:
            return AnalyzerOutput(
                id=self.id, name=self.name, score=0.5, confidence=0.2,
                findings=["Image too small for reliable DCT statistics"], details={},
            )

        hist = _first_digit_hist(ac)
        ben = _benford()
        chi = float(np.sum((hist - ben) ** 2 / (ben + 1e-12)))
        ac_std = float(ac.std())
        ac_mean_abs = float(np.mean(np.abs(ac)))
        near_zero = float(np.mean(np.abs(ac) < 1.0))
        abs_ac = np.abs(ac) + 1e-8
        geo = float(np.exp(np.mean(np.log(abs_ac))))
        arith = float(np.mean(abs_ac))
        flatness = float(geo / (arith + 1e-12))
        periodicity = _ac_periodicity(ac)

        score = 0.4
        confidence = 0.55

        if chi > 0.075:
            score = 0.70
            confidence = 0.62
            findings.append(f"AC first-digit distribution diverges from Benford (χ²≈{chi:.3f})")
        elif chi > 0.042:
            score = 0.56
            findings.append(f"Moderate Benford deviation (χ²≈{chi:.3f})")
        else:
            score = 0.28
            findings.append(f"AC digits closer to Benford (χ²≈{chi:.3f})")

        if near_zero > 0.70:
            score = min(1.0, score + 0.16)
            confidence = min(0.88, confidence + 0.12)
            findings.append(
                f"High fraction of near-zero AC coefficients ({near_zero:.0%}) — overly smooth blocks"
            )
        elif near_zero < 0.45 and ac_std > 8:
            score = max(0.0, score - 0.1)
            findings.append("Rich AC energy more typical of natural/camera imagery")

        if flatness < 0.18 and near_zero > 0.55:
            score = min(1.0, score + 0.08)
            findings.append(f"Low AC spectral flatness ({flatness:.3f}) — sparse coefficient energy")

        if periodicity > 0.35:
            score = min(1.0, score + 0.07)
            confidence = min(0.9, confidence + 0.05)
            findings.append(
                f"8x8 block periodicity in AC magnitudes ({periodicity:.2f}) — blocking artifact; "
                "a weak recompression cue, not a double-quantization test"
            )

        if via_jpeg:
            findings.append("Source was non-JPEG; analyzed via controlled JPEG pass")

        return AnalyzerOutput(
            id=self.id, name=self.name,
            score=float(np.clip(score, 0, 1)), confidence=float(np.clip(confidence, 0, 1)),
            findings=findings,
            details={
                "benford_chi": chi, "near_zero_ac_frac": near_zero, "ac_std": ac_std,
                "ac_mean_abs": ac_mean_abs, "ac_spectral_flatness": flatness,
                "ac_periodicity": periodicity, "via_jpeg_pass": via_jpeg,
                "digit_hist": hist.tolist(),
            },
        )
