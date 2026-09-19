"""OCR adapter wrapping pytesseract (optional system tesseract)."""

from __future__ import annotations

import numpy as np


class PytesseractOcrEngine:
    def is_available(self) -> bool:
        try:
            import pytesseract  # noqa: F401

            return True
        except Exception:
            return False

    def image_to_string(self, image: np.ndarray, config: str = "--psm 6") -> str:
        import pytesseract

        return pytesseract.image_to_string(image, config=config)
