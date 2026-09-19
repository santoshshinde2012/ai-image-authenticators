"""FastAPI dependency accessors (wired from app.state)."""

from __future__ import annotations

from fastapi import Request

from ai_image_authenticator.application.services.analysis import AnalysisService
from ai_image_authenticator.core.config import Settings
from ai_image_authenticator.domain.ports import ArtifactStore


def get_analysis_service(request: Request) -> AnalysisService:
    return request.app.state.analysis_service


def get_artifact_store(request: Request) -> ArtifactStore:
    return request.app.state.artifact_store


def get_analyzer_ids(request: Request) -> list[str]:
    return list(request.app.state.analyzer_ids)


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings
