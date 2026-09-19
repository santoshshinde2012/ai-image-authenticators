"""Concrete forensic analyzers + open-closed registry."""

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

__all__ = [
    "AnalyzerRegistry",
    "BayarPredictionResidual",
    "DCTJpegStats",
    "ErrorLevelAnalysis",
    "FrequencySpectrum",
    "LocalCorrelationAnalyzer",
    "MetadataForensics",
    "NoiseResidual",
    "ProvenanceC2PA",
    "SRMResidualAnalyzer",
    "ScreenshotHeuristic",
    "TextureGradient",
    "VisibleLabelOCR",
]
