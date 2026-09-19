"""Domain value objects. No I/O, no HTTP, no fusion policy."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from PIL import Image

from ai_image_authenticator.domain.verdict import Verdict


@dataclass
class AnalyzerOutput:
    """Single-analyzer result. Higher score = more likely AI/synthetic."""

    id: str
    name: str
    score: float
    confidence: float
    findings: list[str] = field(default_factory=list)
    visualization: bytes | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class SignalScore:
    """Fused view of one analyzer (score + effective weight + optional viz URL)."""

    id: str
    name: str
    score: float
    confidence: float
    weight: float
    findings: list[str] = field(default_factory=list)
    viz_url: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class AnalysisOutcome:
    verdict: Verdict
    ai_probability: float
    confidence: float
    summary: str
    signals: list[SignalScore]
    limitations: list[str]
    filename: str
    dimensions: list[int]
    screenshot_detected: bool = False
    analysis_ms: int = 0
    evidence_paths: list[str] = field(default_factory=list)
    fusion_reasons: list[str] = field(default_factory=list)
    challenge_flags: list[str] = field(default_factory=list)
    failure_modes: list[str] = field(default_factory=list)


@dataclass
class Artifact:
    data: bytes
    content_type: str
    created_at: float
    filename: str = "artifact.png"


@dataclass
class LoadedImage:
    image: Image.Image
    rgb: np.ndarray
    raw_bytes: bytes
    filename: str
    width: int
    height: int
    frame_count: int = 1
    # Human-readable notes about how decoding changed the input (surfaced as failure modes)
    decode_notes: list[str] = field(default_factory=list)
