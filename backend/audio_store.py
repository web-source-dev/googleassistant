"""Persist spoken microphone clips and a small index of metadata."""

from __future__ import annotations

import json
import logging
import re
import threading
import uuid
import wave
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path 
from typing import Any

logger = logging.getLogger(__name__)

_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{8,64}$")
MAX_CLIPS = 200
MAX_WAV_BYTES = 2 * 1024 * 1024
MIN_WAV_BYTES = 256


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def wav_duration_ms(data: bytes) -> int:
    try:
        with wave.open(BytesIO(data), "rb") as wav:
            rate = wav.getframerate() or 1
            return int(1000 * wav.getnframes() / rate)
    except Exception:
        return 0


class AudioStore:
    def __init__(self, root: Path, max_clips: int = MAX_CLIPS) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.index_path = self.root / "index.json"
        self.max_clips = max_clips
        self._lock = threading.Lock()
        self._items: list[dict[str, Any]] = self._load()

    def _load(self) -> list[dict[str, Any]]:
        if not self.index_path.exists():
            return []
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [item for item in data if isinstance(item, dict) and item.get("id")]
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not read audio index: %s", exc)
        return []

    def _persist(self) -> None:
        tmp = self.index_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self._items, indent=2), encoding="utf-8")
        tmp.replace(self.index_path)

    def save(
        self,
        wav: bytes,
        *,
        transcript: str = "",
        wake: bool = False,
        hostname: str = "",
        username: str = "",
    ) -> dict[str, Any]:
        if not wav or len(wav) < MIN_WAV_BYTES:
            raise ValueError("Audio clip is empty")
        if len(wav) > MAX_WAV_BYTES:
            raise ValueError("Audio clip is too large")
        if wav[:4] != b"RIFF":
            raise ValueError("Audio clip must be WAV")

        clip_id = uuid.uuid4().hex
        path = self.root / f"{clip_id}.wav"
        path.write_bytes(wav)

        item = {
            "id": clip_id,
            "transcript": (transcript or "").strip()[:2000] or "Speaking",
            "wake": bool(wake),
            "hostname": (hostname or "pc")[:80],
            "username": (username or "user")[:80],
            "duration_ms": wav_duration_ms(wav),
            "size": len(wav),
            "created_at": _iso(),
            "url": f"/api/audio/{clip_id}",
        }

        with self._lock:
            self._prune_locked()
            self._items.insert(0, item)
            removed = self._items[self.max_clips :]
            self._items = self._items[: self.max_clips]
            self._persist()

        for old in removed:
            self._delete_file(str(old.get("id") or ""))

        logger.info("Saved voice clip %s (%s ms)", clip_id, item["duration_ms"])
        return item

    def _prune_locked(self) -> None:
        kept: list[dict[str, Any]] = []
        for item in self._items:
            clip_id = str(item.get("id") or "")
            if clip_id and (self.root / f"{clip_id}.wav").is_file():
                kept.append(item)
        if len(kept) != len(self._items):
            self._items = kept
            self._persist()

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        cap = max(1, min(int(limit or 50), self.max_clips))
        with self._lock:
            self._prune_locked()
            return [dict(item) for item in self._items[:cap]]

    def get(self, clip_id: str) -> dict[str, Any] | None:
        if not _ID_RE.match(clip_id):
            return None
        with self._lock:
            self._prune_locked()
            for item in self._items:
                if item.get("id") == clip_id:
                    return dict(item)
        return None

    def wav_path(self, clip_id: str) -> Path | None:
        if not _ID_RE.match(clip_id):
            return None
        path = self.root / f"{clip_id}.wav"
        if path.is_file():
            return path
        return None

    def count(self) -> int:
        with self._lock:
            self._prune_locked()
            return len(self._items)

    def _delete_file(self, clip_id: str) -> None:
        if not _ID_RE.match(clip_id):
            return
        path = self.root / f"{clip_id}.wav"
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("Could not delete old clip %s: %s", clip_id, exc)
