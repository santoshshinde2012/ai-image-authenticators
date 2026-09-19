"""Shared analyzer base. Prefer depending on the Analyzer protocol in services."""

from __future__ import annotations

import numpy as np
from PIL import Image

from ai_image_authenticator.domain.models import AnalyzerOutput


class BaseAnalyzer:
    """Convenience base; Liskov-compatible with Analyzer protocol."""

    id: str = "base"
    name: str = "Base Analyzer"

    def analyze(
        self,
        image: Image.Image,
        rgb: np.ndarray,
        raw_bytes: bytes,
        filename: str,
    ) -> AnalyzerOutput:
        raise NotImplementedError
