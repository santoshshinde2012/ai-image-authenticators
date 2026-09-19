"""HTTP v1 routes only — no fusion / analyzer logic."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response

from ai_image_authenticator.application.services.analysis import AnalysisService
from ai_image_authenticator.core.config import Settings
from ai_image_authenticator.domain.ports import ArtifactStore
from ai_image_authenticator.infrastructure.image_loader import ImageTooLarge, ImageTooSmall
from ai_image_authenticator.interfaces.http.deps import (
    get_analysis_service,
    get_analyzer_ids,
    get_artifact_store,
    get_settings_dep,
)
from ai_image_authenticator.interfaces.http.schemas import AnalysisResult
from ai_image_authenticator.interfaces.http.uploads import read_validated_upload

router = APIRouter(prefix="/api/v1")


@router.get("/health")
def health() -> dict:
    """Liveness — process is up."""
    return {"status": "ok", "service": "ai-image-authenticator", "version": "1.0.0"}


@router.get("/ready")
def ready(request: Request, analyzer_ids: list[str] = Depends(get_analyzer_ids)) -> dict:
    """Readiness — container wired and analyzers registered."""
    has_service = getattr(request.app.state, "analysis_service", None) is not None
    has_store = getattr(request.app.state, "artifact_store", None) is not None
    if not has_service or not has_store or not analyzer_ids:
        raise HTTPException(status_code=503, detail="Service not ready")
    return {
        "status": "ready",
        "service": "ai-image-authenticator",
        "version": "1.0.0",
        "analyzers": analyzer_ids,
        "analyzer_count": len(analyzer_ids),
    }


@router.post("/analyze", response_model=AnalysisResult)
async def analyze(
    file: UploadFile = File(...),
    service: AnalysisService = Depends(get_analysis_service),
    settings: Settings = Depends(get_settings_dep),
) -> AnalysisResult:
    data, filename = await read_validated_upload(
        file,
        max_bytes=settings.max_upload_bytes,
        allowed_types=settings.allowed_content_types,
    )
    try:
        outcome = service.analyze_bytes(data, filename)
        return AnalysisResult.from_outcome(outcome)
    except ImageTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except ImageTooSmall as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — surface as HTTP error
        # Decoder messages can leak internals; only show them outside prod
        detail = "Failed to analyze image"
        if settings.environment != "prod":
            detail = f"{detail}: {exc}"
        raise HTTPException(status_code=400, detail=detail) from exc


@router.get("/artifacts/{artifact_id}")
def get_artifact(
    artifact_id: str,
    store: ArtifactStore = Depends(get_artifact_store),
) -> Response:
    item = store.get(artifact_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Artifact not found or expired")
    return Response(
        content=item.data,
        media_type=item.content_type,
        headers={"Cache-Control": "private, max-age=300"},
    )
