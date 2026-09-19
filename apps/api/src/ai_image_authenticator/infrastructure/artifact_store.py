"""In-memory artifact store with TTL + max-entry eviction."""

from __future__ import annotations

import threading
import time
import uuid

from ai_image_authenticator.domain.models import Artifact


class InMemoryArtifactStore:
    def __init__(self, ttl_seconds: int = 3600, max_entries: int = 256) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_entries = max(1, max_entries)
        self._items: dict[str, Artifact] = {}
        self._lock = threading.Lock()

    def put(self, data: bytes, content_type: str = "image/png", filename: str = "artifact.png") -> str:
        self.cleanup()
        artifact_id = uuid.uuid4().hex
        with self._lock:
            self._items[artifact_id] = Artifact(
                data=data,
                content_type=content_type,
                created_at=time.time(),
                filename=filename,
            )
            self._evict_overflow_locked()
        return artifact_id

    def get(self, artifact_id: str) -> Artifact | None:
        self.cleanup()
        with self._lock:
            return self._items.get(artifact_id)

    def cleanup(self) -> None:
        now = time.time()
        with self._lock:
            expired = [k for k, v in self._items.items() if now - v.created_at > self.ttl_seconds]
            for k in expired:
                del self._items[k]
            self._evict_overflow_locked()

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)

    def _evict_overflow_locked(self) -> None:
        """Drop oldest entries when over max_entries (caller holds lock)."""
        overflow = len(self._items) - self.max_entries
        if overflow <= 0:
            return
        oldest = sorted(self._items.items(), key=lambda kv: kv[1].created_at)[:overflow]
        for key, _ in oldest:
            del self._items[key]
