"""Upload validation helpers (size, content-type, safe filename)."""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from fastapi import HTTPException, UploadFile

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def safe_filename(name: str | None, fallback: str = "upload.bin") -> str:
    if not name or not name.strip():
        return fallback
    base = PurePosixPath(name.replace("\\", "/")).name
    cleaned = _SAFE_NAME.sub("_", base).strip("._")
    if not cleaned or cleaned in {".", ".."}:
        return fallback
    return cleaned[:200]


def sniff_content_type(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if len(data) >= 12 and data[4:8] == b"ftyp" and data[8:12] in (b"avif", b"avis"):
        return "image/avif"
    return None


async def read_validated_upload(
    file: UploadFile,
    *,
    max_bytes: int,
    allowed_types: list[str],
) -> tuple[bytes, str]:
    """Return (bytes, safe_filename) or raise HTTPException."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename required")
    filename = safe_filename(file.filename)

    declared = (file.content_type or "").split(";")[0].strip().lower()
    if declared and declared not in allowed_types and declared != "application/octet-stream":
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported content type: {declared}. Allowed: {', '.join(allowed_types)}",
        )

    # Read at most one byte past the cap so an oversized upload never lands in memory
    data = await file.read(max_bytes + 1)
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large (max {max_bytes} bytes)",
        )

    sniffed = sniff_content_type(data)
    if sniffed is None or sniffed not in allowed_types:
        raise HTTPException(
            status_code=415,
            detail=(
                "File bytes are not a supported image type "
                f"({', '.join(t.split('/')[-1] for t in allowed_types)}); HEIC is not supported"
            ),
        )
    if declared and declared in allowed_types and declared != sniffed:
        raise HTTPException(
            status_code=415,
            detail=f"Content-Type {declared} does not match file contents ({sniffed})",
        )
    return data, filename
