"""Frequency-domain (FFT) spectrum analysis (Durall / aidetect-style classical features).

Adds azimuthal-average power spectrum, high-frequency power ratio, log-log spectral
slope, and residual spikes on top of the existing radial HF/LF + anisotropy cues.
Reference: Durall et al., CVPR 2020 (Watch your Up-Convolution); classical aidetect
spectrum features.
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
        raise RuntimeError("Failed to encode FFT visualization")
    return buf.tobytes()


def _azimuthal_average(power: np.ndarray) -> np.ndarray:
    """Azimuthal (radial) average of a centered 2D power spectrum."""
    cy, cx = np.array(power.shape) // 2
    yy, xx = np.ogrid[: power.shape[0], : power.shape[1]]
    r = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2).astype(np.int32)
    max_r = int(min(cy, cx))
    radial = np.zeros(max_r, dtype=np.float64)
    counts = np.zeros(max_r, dtype=np.int32)
    flat_r = r.ravel()
    flat_p = power.ravel()
    for i in range(flat_r.size):
        ri = flat_r[i]
        if 0 <= ri < max_r:
            radial[ri] += flat_p[i]
            counts[ri] += 1
    counts = np.maximum(counts, 1)
    return radial / counts


def _log_log_slope(radial_power: np.ndarray) -> float:
    """Fit log(power) ~ a * log(freq) over mid band; return slope a."""
    n = radial_power.size
    if n < 16:
        return 0.0
    lo = max(2, n // 10)
    hi = max(lo + 8, int(n * 0.6))
    hi = min(hi, n)
    if hi - lo < 8:
        return 0.0
    freqs = np.arange(lo, hi, dtype=np.float64)
    vals = radial_power[lo:hi]
    mask = vals > 1e-12
    if mask.sum() < 8:
        return 0.0
    x = np.log(freqs[mask])
    y = np.log(vals[mask])
    a, _b = np.polyfit(x, y, 1)
    return float(a)


def _residual_spike_score(radial_power: np.ndarray) -> float:
    """Detect spikes vs smooth log-log trend (upsampler lattice / checker peaks)."""
    n = radial_power.size
    if n < 24:
        return 0.0
    lo, hi = max(2, n // 8), int(n * 0.7)
    freqs = np.arange(lo, hi, dtype=np.float64)
    vals = np.maximum(radial_power[lo:hi], 1e-12)
    x = np.log(freqs)
    y = np.log(vals)
    a, b = np.polyfit(x, y, 1)
    trend = np.exp(a * x + b)
    resid = (vals - trend) / (trend + 1e-12)
    # Spike score: fraction of bins exceeding 2.5x trend
    return float(np.mean(resid > 1.5))


class FrequencySpectrum(BaseAnalyzer):
    id = "fft"
    name = "Frequency Spectrum (FFT)"

    def analyze(
        self, image: Image.Image, rgb: np.ndarray, raw_bytes: bytes, filename: str
    ) -> AnalyzerOutput:
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
        max_side = 1024
        h, w = gray.shape
        scale = min(1.0, max_side / max(h, w))
        if scale < 1.0:
            gray = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

        f = np.fft.fft2(gray)
        fshift = np.fft.fftshift(f)
        magnitude = np.abs(fshift)
        power = magnitude ** 2
        mag_log = np.log1p(magnitude)

        mag_norm = cv2.normalize(mag_log, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
        spectrum_color = cv2.applyColorMap(mag_norm, cv2.COLORMAP_MAGMA)

        # Durall-style azimuthal average of power
        azimuthal = _azimuthal_average(power)
        max_r = azimuthal.size
        log_log_slope = _log_log_slope(azimuthal)
        spike_frac = _residual_spike_score(azimuthal)

        # Also keep log-magnitude radial profile for HF/LF ratio (prior path)
        cy, cx = np.array(mag_log.shape) // 2
        yy, xx = np.ogrid[: mag_log.shape[0], : mag_log.shape[1]]
        r = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2).astype(np.int32)
        radial = np.zeros(max_r, dtype=np.float64)
        flat_r = r.ravel()
        flat_m = mag_log.ravel()
        for radius in range(max_r):
            mask = flat_r == radius
            if mask.any():
                radial[radius] = flat_m[mask].mean()

        if max_r > 10:
            low = radial[: max(3, max_r // 8)].mean()
            high = radial[int(max_r * 0.55) :].mean()
            mid = radial[int(max_r * 0.25) : int(max_r * 0.45)].mean()
            mid_hi = radial[int(max_r * 0.35) : int(max_r * 0.5)].mean()
            mid_lo = radial[int(max_r * 0.15) : int(max_r * 0.3)].mean()
            mid_notch = float((mid_lo - mid_hi) / (mid_lo + 1e-6))
            # Power-based HF ratio (Durall / aidetect)
            p_low = float(azimuthal[: max(3, max_r // 8)].mean())
            p_high = float(azimuthal[int(max_r * 0.55) :].mean())
            hf_power_ratio = float(p_high / (p_low + 1e-12))
        else:
            low, high, mid, mid_notch = 1.0, 1.0, 1.0, 0.0
            hf_power_ratio = 1.0

        hf_ratio = float(high / (low + 1e-6))

        center_row = mag_log[cy, :]
        center_col = mag_log[:, cx]
        diag = np.array(
            [
                mag_log[cy + i, cx + i]
                for i in range(-min(cy, cx) // 2, min(cy, cx) // 2)
                if i != 0
            ]
        )
        axis_boost = float((center_row.mean() + center_col.mean()) / (2 * (diag.mean() + 1e-6)))

        anisotropy = 0.0
        if max_r > 30:
            rr = r.astype(np.float64)
            ang = np.arctan2(yy - cy, xx - cx)
            ring = (rr > max_r * 0.25) & (rr < max_r * 0.55)
            if ring.any():
                bins = np.linspace(-np.pi, np.pi, 17)
                digitized = np.digitize(ang[ring].ravel(), bins)
                vals = mag_log[ring].ravel()
                means = []
                for b in range(1, 17):
                    sel = digitized == b
                    if sel.any():
                        means.append(float(vals[sel].mean()))
                if len(means) >= 8:
                    anisotropy = float(np.std(means) / (np.mean(means) + 1e-6))

        flat = mag_log.ravel()
        z = (flat - flat.mean()) / (flat.std() + 1e-6)
        kurtosis = float(np.mean(z**4) - 3.0)

        findings: list[str] = []
        score = 0.4
        confidence = 0.55

        if hf_ratio < 0.52:
            score = 0.74
            confidence = 0.68
            findings.append(
                f"Attenuated high-frequency energy (HF/LF={hf_ratio:.2f}) — "
                "common after generative synthesis/upsampling"
            )
        elif hf_ratio < 0.68:
            score = 0.58
            findings.append(f"Mildly reduced high-frequency content (HF/LF={hf_ratio:.2f})")
        else:
            score = 0.30
            findings.append(f"Healthy high-frequency content (HF/LF={hf_ratio:.2f})")

        # Durall: unnatural spectral decay (GAN up-convolutions often flatten high bands)
        # Natural photos: slope typically steeply negative; many GANs: flatter / broken
        if log_log_slope > -1.2 and hf_ratio < 0.75:
            score = min(1.0, score + 0.09)
            confidence = min(0.9, confidence + 0.06)
            findings.append(
                f"Flattened log-log spectrum slope ({log_log_slope:.2f}) — "
                "Durall-style up-convolution cue"
            )
        elif log_log_slope < -2.8 and hf_ratio < 0.6:
            score = min(1.0, score + 0.05)
            findings.append(f"Very steep spectral decay (slope={log_log_slope:.2f}) with HF loss")

        if spike_frac > 0.08:
            score = min(1.0, score + 0.08)
            confidence = min(0.9, confidence + 0.05)
            findings.append(
                f"Azimuthal power residual spikes ({spike_frac:.0%} of mid-band bins) — "
                "lattice/upsampler peaks"
            )

        if hf_power_ratio < 0.08 and hf_ratio < 0.7:
            score = min(1.0, score + 0.05)
            findings.append(f"Low azimuthal HF power ratio ({hf_power_ratio:.3f})")

        if axis_boost > 1.32:
            score = min(1.0, score + 0.13)
            confidence = min(0.88, confidence + 0.12)
            findings.append(
                f"Elevated axial spectral peaks (axis boost={axis_boost:.2f}) — "
                "possible grid/upsampling artifacts"
            )

        if mid_notch > 0.12 and hf_ratio < 0.7:
            score = min(1.0, score + 0.07)
            findings.append(
                f"Mid-band spectral notch (Δ={mid_notch:.2f}) consistent with frequency-limited synthesis"
            )

        if anisotropy > 0.08 and axis_boost > 1.15:
            score = min(1.0, score + 0.06)
            confidence = min(0.9, confidence + 0.05)
            findings.append(f"Azimuthal anisotropy ({anisotropy:.3f}) — directional spectral bias")

        if kurtosis > 6.0 and axis_boost > 1.2:
            score = min(1.0, score + 0.05)
            findings.append(f"Peaky spectral kurtosis ({kurtosis:.1f}) with axial bias")

        if max_r > 20:
            slope = float(radial[int(max_r * 0.3)] - radial[int(max_r * 0.7)])
            if slope > 1.7 and hf_ratio < 0.65:
                score = min(1.0, score + 0.08)
                findings.append("Sharp radial power roll-off consistent with frequency-limited generation")

        if not findings:
            findings.append("No strong spectral anomalies")

        # Compact azimuthal curve for API (downsample)
        az_ds = azimuthal[:: max(1, max_r // 32)] if max_r else np.array([])
        az_ds = [float(x) for x in az_ds[:32]]

        return AnalyzerOutput(
            id=self.id,
            name=self.name,
            score=float(np.clip(score, 0, 1)),
            confidence=float(np.clip(confidence, 0, 1)),
            findings=findings,
            visualization=_to_png_bytes(spectrum_color),
            details={
                "hf_lf_ratio": hf_ratio,
                "axis_boost": axis_boost,
                "mid_band": float(mid),
                "mid_notch": mid_notch,
                "azimuthal_anisotropy": anisotropy,
                "spectral_kurtosis": kurtosis,
                "log_log_slope": log_log_slope,
                "hf_power_ratio": hf_power_ratio,
                "azimuthal_spike_fraction": spike_frac,
                "azimuthal_avg_power_ds": az_ds,
                "citation": "Durall CVPR 2020; aidetect-style classical spectrum features",
            },
        )
