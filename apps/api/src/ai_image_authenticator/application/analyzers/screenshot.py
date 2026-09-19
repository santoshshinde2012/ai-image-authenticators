"""Screenshot / UI chrome heuristic — adjusts interpretation, not raw AI score fusion weight."""

from __future__ import annotations

import cv2
import numpy as np
from PIL import Image

from ai_image_authenticator.application.analyzers.base import BaseAnalyzer
from ai_image_authenticator.domain.models import AnalyzerOutput


class ScreenshotHeuristic(BaseAnalyzer):
    id = "screenshot"
    name = "Screenshot Heuristic"

    def analyze(self, image: Image.Image, rgb: np.ndarray, raw_bytes: bytes, filename: str) -> AnalyzerOutput:
        h, w = rgb.shape[:2]
        aspect = w / max(h, 1)
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)

        # Flat border / chrome: very uniform top/bottom strips
        strip = max(8, h // 40)
        top = gray[:strip, :]
        bottom = gray[-strip:, :]
        left = gray[:, :strip]
        right = gray[:, -strip:]
        border_std = float(np.mean([top.std(), bottom.std(), left.std(), right.std()]))

        # Large near-flat regions (UI panels)
        small = cv2.resize(gray, (128, 128), interpolation=cv2.INTER_AREA)
        # Local variance via blur difference
        blur = cv2.GaussianBlur(small.astype(np.float32), (5, 5), 0)
        local_var = cv2.blur((small.astype(np.float32) - blur) ** 2, (7, 7))
        flat_frac = float(np.mean(local_var < 8.0))

        # Horizontal edge density (UI lines / tweet chrome)
        edges = cv2.Canny(gray, 80, 160)
        horiz = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        vert = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        horiz_energy = float(np.mean(np.abs(horiz)))
        vert_energy = float(np.mean(np.abs(vert)))
        edge_density = float(edges.mean() / 255.0)

        # Color palette simplicity in corners (status bars often solid)
        corner = rgb[: max(20, h // 20), : max(20, w // 20)]
        corner_colors = len(np.unique(corner.reshape(-1, 3), axis=0))

        # Filename hints
        name_l = (filename or "").lower()
        name_hint = any(k in name_l for k in ("screenshot", "screen shot", "tweet", "twitter", "x.com", "capture"))

        score_ui = 0.0
        findings = []
        top_mean = float(top.mean())
        body_mean = float(gray[strip * 2 :, :].mean()) if h > strip * 3 else float(gray.mean())
        if border_std < 18:
            score_ui += 0.25
            findings.append(f"Uniform borders (std={border_std:.1f}) suggest UI chrome / capture")
        if abs(top_mean - body_mean) > 40 and top.std() < 25:
            score_ui += 0.2
            findings.append("Distinct top chrome bar vs body (status/nav pattern)")
        if flat_frac > 0.28:
            score_ui += 0.3
            findings.append(f"Large flat UI-like regions ({flat_frac:.0%} of downscaled area)")
        if 0.4 < aspect < 0.7 or aspect > 1.6:
            score_ui += 0.1
            findings.append(f"Aspect ratio {aspect:.2f} common for phone/desktop screenshots")
        if horiz_energy > vert_energy * 1.15 and edge_density > 0.04:
            score_ui += 0.15
            findings.append("Horizontal structure / separators consistent with social UI layouts")
        if corner_colors < 40:
            score_ui += 0.1
            findings.append("Low corner color diversity (status/nav bar)")
        if name_hint:
            score_ui += 0.2
            findings.append("Filename suggests screenshot/social capture")

        # Pixel-perfect solid runs (text antialiasing + flat bg)
        row_runs = 0
        for row in gray[:: max(1, h // 100)]:
            if np.mean(np.abs(np.diff(row.astype(np.int16))) < 2) > 0.7:
                row_runs += 1
        if row_runs > 15:
            score_ui += 0.1
            findings.append("Many near-constant scanlines — UI / text background pattern")

        screenshot_likelihood = float(np.clip(score_ui, 0, 1))
        # Flat synthetic art often has uniform borders; require a chrome/layout cue
        # (aspect, top bar, horizontal UI energy, filename) — not flatness alone.
        chrome_cues = 0
        if abs(top_mean - body_mean) > 40 and top.std() < 25:
            chrome_cues += 1
        if 0.4 < aspect < 0.7 or aspect > 1.6:
            chrome_cues += 1
        if horiz_energy > vert_energy * 1.15 and edge_density > 0.04:
            chrome_cues += 1
        if name_hint:
            chrome_cues += 1
        is_screenshot = screenshot_likelihood >= 0.55 and chrome_cues >= 2

        # This analyzer's "score" is NOT AI probability — fusion treats it specially.
        # We still return a soft AI-leaning score only when screenshot + smooth illustration cues exist,
        # but primarily encode screenshot_likelihood in details.
        ai_score = 0.5  # neutral toward AI; fusion uses screenshot flag to adjust confidence
        if is_screenshot:
            findings.insert(
                0,
                "Screenshot-like capture detected: do not treat as a camera photo; "
                "embedded illustrations may still be AI-generated",
            )
            ai_score = 0.52  # slight lean — social posts often contain synthetic media
            confidence = 0.75
        else:
            findings.append("No strong screenshot/UI chrome signals")
            confidence = 0.5
            ai_score = 0.45

        return AnalyzerOutput(
            id=self.id,
            name=self.name,
            score=float(np.clip(ai_score, 0, 1)),
            confidence=float(np.clip(confidence, 0, 1)),
            findings=findings,
            details={
                "screenshot_likelihood": screenshot_likelihood,
                "is_screenshot": is_screenshot,
                "chrome_cues": chrome_cues,
                "flat_fraction": flat_frac,
                "border_std": border_std,
                "aspect": aspect,
                "edge_density": edge_density,
            },
        )
