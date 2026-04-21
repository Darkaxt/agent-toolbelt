from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .models import IntentMode, IntentProfile


class IntentCache:
    def __init__(self, root: Path, ttl: timedelta = timedelta(hours=24)) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.ttl = ttl

    def _cache_path(self, query: str, marketplace: str, mode: IntentMode) -> Path:
        key = f"{query.strip().casefold()}::{marketplace}::{mode.value}"
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.root / f"{digest}.json"

    def save(self, profile: IntentProfile) -> None:
        path = self._cache_path(profile.query, profile.marketplace, profile.mode)
        path.write_text(json.dumps(profile.to_dict(), indent=2), encoding="utf-8")

    def load(self, query: str, marketplace: str, mode: IntentMode) -> IntentProfile | None:
        path = self._cache_path(query, marketplace, mode)
        if not path.exists():
            return None

        payload = json.loads(path.read_text(encoding="utf-8"))
        profile = IntentProfile.from_dict(payload)
        age = datetime.now(UTC) - profile.created_at.astimezone(UTC)
        if age > self.ttl:
            return None
        return profile
