"""Small ISP-friendly ports. Implementations live in analyzers / infrastructure / services."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np
from PIL import Image

from ai_image_authenticator.domain.models import AnalysisOutcome, AnalyzerOutput, Artifact


@runtime_checkable
class Analyzer(Protocol):
    """One forensic signal. Implementations must not fuse or persist artifacts."""

    id: str
    name: str

    def analyze(
        self,
        image: Image.Image,
        rgb: np.ndarray,
        raw_bytes: bytes,
        filename: str,
    ) -> AnalyzerOutput: ...


@runtime_checkable
class ArtifactStore(Protocol):
    """Binary visualization storage only."""

    def put(self, data: bytes, content_type: str = "image/png", filename: str = "artifact.png") -> str: ...

    def get(self, artifact_id: str) -> Artifact | None: ...


@runtime_checkable
class FusionPolicy(Protocol):
    """Combine analyzer outputs into a verdict. No I/O."""

    def fuse(
        self,
        outputs: list[AnalyzerOutput],
        viz_urls: dict[str, str | None],
        filename: str,
        dimensions: list[int],
        analysis_ms: int,
    ) -> AnalysisOutcome: ...


@runtime_checkable
class OcrEngine(Protocol):
    """Pixel-to-text port. Labels analyzer depends on this, not pytesseract."""

    def image_to_string(self, image: np.ndarray, config: str = "--psm 6") -> str: ...

    def is_available(self) -> bool: ...
