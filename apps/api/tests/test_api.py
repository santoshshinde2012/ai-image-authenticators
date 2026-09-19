import io

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

from ai_image_authenticator.core.config import Settings
from ai_image_authenticator.domain.verdict import verdict_from_probability
from ai_image_authenticator.main import create_app


def _png_bytes(size: int = 32) -> bytes:
    arr = np.zeros((size, size, 3), dtype=np.uint8)
    arr[:, :, 0] = 200
    buf = io.BytesIO()
    Image.fromarray(arr, mode="RGB").save(buf, format="PNG")
    return buf.getvalue()


def test_health():
    client = TestClient(create_app())
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["service"] == "ai-image-authenticator"
    assert "analyzers" not in body  # analyzers live on /ready
    assert "X-Request-ID" in res.headers
    assert res.headers.get("X-Content-Type-Options") == "nosniff"
    assert res.headers.get("X-Frame-Options") == "DENY"
    assert res.headers.get("Referrer-Policy") == "no-referrer"


def test_ready():
    client = TestClient(create_app())
    res = client.get("/api/v1/ready")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ready"
    assert "labels" in body["analyzers"]
    assert "metadata" in body["analyzers"]
    assert "provenance" in body["analyzers"]
    assert body["analyzer_count"] == 12


def test_analyze_rejects_non_image_bytes():
    client = TestClient(create_app())
    res = client.post(
        "/api/v1/analyze",
        files={"file": ("notes.txt", b"not an image", "text/plain")},
    )
    assert res.status_code == 415
    body = res.json()
    assert body["error"] is True
    assert "detail" in body
    assert body.get("request_id")


def test_analyze_rejects_oversize():
    settings = Settings(max_upload_bytes=64)
    client = TestClient(create_app(settings=settings))
    # Valid PNG but larger than 64 bytes
    data = _png_bytes(64)
    assert len(data) > 64
    res = client.post(
        "/api/v1/analyze",
        files={"file": ("big.png", data, "image/png")},
    )
    assert res.status_code == 413
    assert res.json()["error"] is True


def test_analyze_accepts_png():
    client = TestClient(create_app())
    data = _png_bytes(48)
    res = client.post(
        "/api/v1/analyze",
        files={"file": ("sample.png", data, "image/png")},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["verdict"] == verdict_from_probability(body["ai_probability"]).value
    assert len(body["signals"]) == 12
    assert "challenge_flags" in body
    assert isinstance(body["challenge_flags"], list)
    assert "failure_modes" in body
    assert isinstance(body["failure_modes"], list)
    assert len(body["failure_modes"]) >= 1  # static catalog always present
    # Probe output must not pollute public signal ids
    signal_ids = {s["id"] for s in body["signals"]}
    assert "_probes" not in signal_ids
