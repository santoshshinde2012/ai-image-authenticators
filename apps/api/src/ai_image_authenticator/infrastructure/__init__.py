"""Adapters: storage, image I/O, OCR."""

from ai_image_authenticator.infrastructure.artifact_store import InMemoryArtifactStore
from ai_image_authenticator.infrastructure.image_loader import load_image_bytes
from ai_image_authenticator.infrastructure.ocr import PytesseractOcrEngine

__all__ = ["InMemoryArtifactStore", "PytesseractOcrEngine", "load_image_bytes"]
