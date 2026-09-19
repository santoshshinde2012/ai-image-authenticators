"""DI container — wire ports to concrete adapters."""

from __future__ import annotations

from dataclasses import dataclass

from ai_image_authenticator.application.analyzers.bayar import BayarPredictionResidual
from ai_image_authenticator.application.analyzers.dct import DCTJpegStats
from ai_image_authenticator.application.analyzers.ela import ErrorLevelAnalysis
from ai_image_authenticator.application.analyzers.fft import FrequencySpectrum
from ai_image_authenticator.application.analyzers.labels import VisibleLabelOCR
from ai_image_authenticator.application.analyzers.local_corr import LocalCorrelationAnalyzer
from ai_image_authenticator.application.analyzers.metadata import MetadataForensics
from ai_image_authenticator.application.analyzers.noise import NoiseResidual
from ai_image_authenticator.application.analyzers.provenance import ProvenanceC2PA
from ai_image_authenticator.application.analyzers.registry import AnalyzerRegistry
from ai_image_authenticator.application.analyzers.screenshot import ScreenshotHeuristic
from ai_image_authenticator.application.analyzers.srm import SRMResidualAnalyzer
from ai_image_authenticator.application.analyzers.texture import TextureGradient
from ai_image_authenticator.application.services.analysis import AnalysisService
from ai_image_authenticator.application.services.fusion import WeightedFusionPolicy
from ai_image_authenticator.core.config import Settings, get_settings
from ai_image_authenticator.domain.ports import ArtifactStore
from ai_image_authenticator.infrastructure.artifact_store import InMemoryArtifactStore
from ai_image_authenticator.infrastructure.ocr import PytesseractOcrEngine


@dataclass
class AppContainer:
    analysis_service: AnalysisService
    artifact_store: ArtifactStore
    registry: AnalyzerRegistry
    analyzer_ids: list[str]
    settings: Settings


def build_registry(ocr: PytesseractOcrEngine | None = None) -> AnalyzerRegistry:
    """Register analyzers. Adding a signal = new class + register() here (OCP)."""
    ocr_engine = ocr or PytesseractOcrEngine()
    registry = AnalyzerRegistry()
    registry.register(MetadataForensics())
    registry.register(ProvenanceC2PA())
    registry.register(VisibleLabelOCR(ocr=ocr_engine))
    registry.register(ErrorLevelAnalysis())
    registry.register(FrequencySpectrum())
    registry.register(DCTJpegStats())
    registry.register(NoiseResidual())
    registry.register(SRMResidualAnalyzer())
    registry.register(BayarPredictionResidual())
    registry.register(LocalCorrelationAnalyzer())
    registry.register(TextureGradient())
    registry.register(ScreenshotHeuristic())
    return registry


def build_content_analyzers() -> list:
    """Analyzers re-run on content crop when screenshot chrome dilutes signals."""
    return [
        FrequencySpectrum(),
        NoiseResidual(),
        SRMResidualAnalyzer(),
        BayarPredictionResidual(),
        LocalCorrelationAnalyzer(),
        TextureGradient(),
        ErrorLevelAnalysis(),
    ]


def create_container(
    artifact_store: ArtifactStore | None = None,
    registry: AnalyzerRegistry | None = None,
    settings: Settings | None = None,
) -> AppContainer:
    cfg = settings or get_settings()
    store = artifact_store or InMemoryArtifactStore(
        ttl_seconds=cfg.artifact_ttl_seconds,
        max_entries=cfg.artifact_max_entries,
    )
    reg = registry or build_registry()
    fusion = WeightedFusionPolicy()
    content = build_content_analyzers()
    service = AnalysisService(
        analyzers=reg.all(),
        fusion=fusion,
        artifacts=store,
        content_analyzers=content,
        probe_analyzers=content,  # JPEG Q=75/85 laundering + shift probes
        max_image_pixels=cfg.max_image_pixels,
    )
    return AppContainer(
        analysis_service=service,
        artifact_store=store,
        registry=reg,
        analyzer_ids=reg.ids(),
        settings=cfg,
    )
