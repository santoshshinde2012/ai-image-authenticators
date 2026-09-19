from ai_image_authenticator.core.config import Settings
from ai_image_authenticator.infrastructure.artifact_store import InMemoryArtifactStore


def test_settings_defaults(monkeypatch):
    for var in ("AIAUTH_ENVIRONMENT", "AIAUTH_MAX_IMAGE_PIXELS", "AIAUTH_ALLOWED_CONTENT_TYPES"):
        monkeypatch.delenv(var, raising=False)
    s = Settings(_env_file=None)  # defaults only, whatever a developer's .env says
    assert s.port == 8000
    assert s.max_upload_bytes == 25 * 1024 * 1024
    assert "image/png" in s.allowed_content_types
    assert "image/avif" in s.allowed_content_types
    assert s.max_image_pixels == 50_000_000
    assert s.environment == "dev"


def test_settings_environment_override(monkeypatch):
    monkeypatch.setenv("AIAUTH_ENVIRONMENT", "prod")
    monkeypatch.setenv("AIAUTH_MAX_IMAGE_PIXELS", "1000000")
    s = Settings()
    assert s.environment == "prod"
    assert s.max_image_pixels == 1_000_000


def test_settings_csv_cors(monkeypatch):
    monkeypatch.setenv("AIAUTH_CORS_ORIGINS", "http://a.example,http://b.example")
    # Clear lru_cache is not needed — construct Settings directly
    s = Settings()
    assert s.cors_origins == ["http://a.example", "http://b.example"]


def test_artifact_store_max_entries():
    store = InMemoryArtifactStore(ttl_seconds=3600, max_entries=3)
    ids = [store.put(b"x" + bytes([i]), filename=f"{i}.bin") for i in range(5)]
    assert len(store) == 3
    # Oldest three evicted; last three remain
    assert store.get(ids[0]) is None
    assert store.get(ids[1]) is None
    assert store.get(ids[2]) is not None
    assert store.get(ids[4]) is not None


def test_safe_filename():
    from ai_image_authenticator.interfaces.http.uploads import safe_filename

    assert safe_filename("../../etc/passwd") == "passwd"
    assert safe_filename("weird name!!.PNG") == "weird_name_.PNG"
    assert safe_filename(None) == "upload.bin"
