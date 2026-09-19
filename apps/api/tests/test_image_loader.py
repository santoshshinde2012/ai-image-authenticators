"""Decode normalization and upload limits (docs/gap-analysis.md P0-4, P1-5)."""

from __future__ import annotations

import io
import zlib

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from ai_image_authenticator.core.config import Settings
from ai_image_authenticator.infrastructure.image_loader import (
    ImageTooLarge,
    ImageTooSmall,
    load_image_bytes,
)
from ai_image_authenticator.interfaces.http.uploads import sniff_content_type
from ai_image_authenticator.main import create_app


def _encode(img: Image.Image, fmt: str = "PNG", **kw) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format=fmt, **kw)
    return buf.getvalue()


def _flat_png(width: int, height: int) -> bytes:
    """A tiny file that decodes to a large canvas (decompression-bomb shape)."""
    raw = zlib.compress(b"".join(b"\x00" + b"\x80" * width for _ in range(height)), 9)

    def chunk(tag: bytes, body: bytes) -> bytes:
        return len(body).to_bytes(4, "big") + tag + body + zlib.crc32(tag + body).to_bytes(4, "big")

    header = width.to_bytes(4, "big") + height.to_bytes(4, "big") + bytes([8, 0, 0, 0, 0])
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", raw) + chunk(b"IEND", b"")


def test_pixel_cap_rejects_before_decoding():
    data = _flat_png(6000, 6000)  # 36 MP in a few dozen KB
    assert len(data) < 200_000
    with pytest.raises(ImageTooLarge):
        load_image_bytes(data, "bomb.png", max_pixels=10_000_000)


def test_tiny_images_are_rejected():
    data = _encode(Image.new("RGB", (16, 16), (10, 20, 30)))
    with pytest.raises(ImageTooSmall):
        load_image_bytes(data, "tiny.png")


def test_sixteen_bit_png_is_scaled_not_clipped():
    arr = np.full((64, 64), 32768, dtype=np.uint16)  # 50% gray
    loaded = load_image_bytes(_encode(Image.fromarray(arr)), "g16.png")
    assert abs(float(loaded.rgb.mean()) - 127.5) < 1.0
    assert any("16-bit" in note for note in loaded.decode_notes)


def test_transparent_pixels_are_composited_over_white():
    rgba = np.zeros((64, 64, 4), dtype=np.uint8)  # black, fully transparent
    rgba[:, :32] = (200, 0, 0, 255)  # opaque red left half
    loaded = load_image_bytes(_encode(Image.fromarray(rgba, "RGBA")), "alpha.png")
    assert loaded.rgb[0, 0].tolist() == [200, 0, 0]
    assert loaded.rgb[0, 63].tolist() == [255, 255, 255]
    assert any("transparent" in note for note in loaded.decode_notes)


def test_opaque_alpha_channel_leaves_pixels_unchanged():
    rgba = np.random.default_rng(0).integers(0, 255, (48, 48, 4), dtype=np.uint8)
    rgba[:, :, 3] = 255
    loaded = load_image_bytes(_encode(Image.fromarray(rgba, "RGBA")), "opaque.png")
    assert np.array_equal(loaded.rgb, rgba[:, :, :3])
    assert loaded.decode_notes == []


def test_exif_orientation_is_applied():
    img = Image.new("RGB", (80, 40), (0, 0, 0))
    img.paste((255, 255, 255), (0, 0, 40, 40))  # white left half
    exif = Image.Exif()
    exif[0x0112] = 6  # rotate 90° clockwise to view
    loaded = load_image_bytes(_encode(img, "JPEG", exif=exif.tobytes(), quality=95), "rot.jpg")
    assert (loaded.width, loaded.height) == (40, 80)
    assert loaded.rgb[5, 20].mean() > 200  # white half is now on top
    assert loaded.image.format == "JPEG"  # container identity survives for the analyzers
    assert any("orientation" in note for note in loaded.decode_notes)


def test_animated_gif_is_flagged_as_first_frame_only():
    frames = [Image.new("RGB", (48, 48), (i * 80, 0, 0)) for i in range(3)]
    buf = io.BytesIO()
    frames[0].save(buf, format="GIF", save_all=True, append_images=frames[1:], duration=50)
    loaded = load_image_bytes(buf.getvalue(), "anim.gif")
    assert loaded.frame_count == 3
    assert any("first frame" in note for note in loaded.decode_notes)


def test_decode_notes_reach_failure_modes():
    frames = [Image.new("RGB", (48, 48), (i * 80, 40, 40)) for i in range(2)]
    buf = io.BytesIO()
    frames[0].save(buf, format="GIF", save_all=True, append_images=frames[1:], duration=50)
    client = TestClient(create_app())
    res = client.post("/api/v1/analyze", files={"file": ("anim.gif", buf.getvalue(), "image/gif")})
    assert res.status_code == 200
    assert any("first frame" in m for m in res.json()["failure_modes"])


def test_avif_is_sniffed():
    data = b"\x00\x00\x00\x1cftypavif" + b"\x00" * 32
    assert sniff_content_type(data) == "image/avif"


def test_api_maps_size_limits_to_status_codes(monkeypatch):
    monkeypatch.setenv("AIAUTH_MAX_IMAGE_PIXELS", "1000000")
    from ai_image_authenticator.core import config

    config.get_settings.cache_clear()
    try:
        client = TestClient(create_app())
        big = client.post(
            "/api/v1/analyze", files={"file": ("big.png", _flat_png(2000, 2000), "image/png")}
        )
        assert big.status_code == 413
        assert "MP" in big.json()["detail"]
        tiny = _encode(Image.new("RGB", (8, 8)))
        small = client.post("/api/v1/analyze", files={"file": ("tiny.png", tiny, "image/png")})
        assert small.status_code == 422
    finally:
        config.get_settings.cache_clear()


def test_upload_byte_cap_is_enforced(monkeypatch):
    monkeypatch.setenv("AIAUTH_MAX_UPLOAD_BYTES", "1000")
    from ai_image_authenticator.core import config

    config.get_settings.cache_clear()
    try:
        client = TestClient(create_app())
        data = _encode(Image.fromarray(np.random.default_rng(1).integers(0, 255, (64, 64, 3), dtype=np.uint8)))
        assert len(data) > 1000
        res = client.post("/api/v1/analyze", files={"file": ("x.png", data, "image/png")})
        assert res.status_code == 413
    finally:
        config.get_settings.cache_clear()


def test_prod_hides_decoder_error_details(monkeypatch):
    truncated = _encode(Image.new("RGB", (64, 64), (1, 2, 3)))[:60]
    for env, leaks in (("dev", True), ("prod", False)):
        monkeypatch.setenv("AIAUTH_ENVIRONMENT", env)
        from ai_image_authenticator.core import config

        config.get_settings.cache_clear()
        try:
            res = TestClient(create_app()).post(
                "/api/v1/analyze", files={"file": ("t.png", truncated, "image/png")}
            )
            assert res.status_code == 400
            assert (res.json()["detail"] != "Failed to analyze image") is leaks
        finally:
            config.get_settings.cache_clear()


def test_settings_fixture_sanity():
    assert Settings().max_image_pixels >= 48_000_000  # full-resolution phone captures fit
