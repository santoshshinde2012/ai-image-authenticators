"""Pydantic HTTP schemas (API boundary)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from ai_image_authenticator.domain.models import AnalysisOutcome

VerdictLiteral = Literal["real", "inconclusive", "likely_ai", "ai_generated"]


class SignalResult(BaseModel):
    id: str
    name: str
    score: float = Field(ge=0.0, le=1.0, description="Higher = more likely AI/synthetic")
    confidence: float = Field(ge=0.0, le=1.0)
    weight: float = Field(ge=0.0, le=1.0)
    findings: list[str] = Field(default_factory=list)
    viz_url: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class AnalysisResult(BaseModel):
    verdict: VerdictLiteral
    ai_probability: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str
    signals: list[SignalResult]
    limitations: list[str]
    filename: str
    dimensions: list[int]
    screenshot_detected: bool = False
    analysis_ms: int = 0
    evidence_paths: list[str] = Field(
        default_factory=list,
        description="Active evidence paths: provenance_contract, pixel_forensic, screenshot_path",
    )
    fusion_reasons: list[str] = Field(
        default_factory=list,
        description="Human-readable fusion policy reasons separating contract vs forensic paths",
    )
    challenge_flags: list[str] = Field(
        default_factory=list,
        description=(
            "Research-challenge markers e.g. compression_laundering, laundering_probe, "
            "generator_shift_uncertainty, dual_layer_provenance_hint, "
            "synthid_layer_not_verified, transform_bias_risk, signal_disagreement, ..."
        ),
    )
    failure_modes: list[str] = Field(
        default_factory=list,
        description=(
            "Short human-readable failure-mode catalog (static honesty + dynamic from flags). "
            "Not a SOTA claim — calibrated inconclusive awareness."
        ),
    )

    @classmethod
    def from_outcome(cls, outcome: AnalysisOutcome) -> AnalysisResult:
        return cls(
            verdict=outcome.verdict.value,  # type: ignore[arg-type]
            ai_probability=outcome.ai_probability,
            confidence=outcome.confidence,
            summary=outcome.summary,
            signals=[
                SignalResult(
                    id=s.id,
                    name=s.name,
                    score=s.score,
                    confidence=s.confidence,
                    weight=s.weight,
                    findings=s.findings,
                    viz_url=s.viz_url,
                    details=s.details,
                )
                for s in outcome.signals
            ],
            limitations=outcome.limitations,
            filename=outcome.filename,
            dimensions=outcome.dimensions,
            screenshot_detected=outcome.screenshot_detected,
            analysis_ms=outcome.analysis_ms,
            evidence_paths=list(getattr(outcome, "evidence_paths", []) or []),
            fusion_reasons=list(getattr(outcome, "fusion_reasons", []) or []),
            challenge_flags=list(getattr(outcome, "challenge_flags", []) or []),
            failure_modes=list(getattr(outcome, "failure_modes", []) or []),
        )
