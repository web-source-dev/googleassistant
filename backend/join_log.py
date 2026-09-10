"""Time-only log of when a live session is joined."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MAX_ITEMS = 200
VIEWER_DEBOUNCE_SEC = 2.5


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime | None = None) -> str:
    return (moment or _now()).isoformat()


def _parse(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


class JoinLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.items: list[dict[str, Any]] = []
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._load()

    def list(self, limit: int = 80) -> list[dict[str, Any]]:
        return self.items[: max(1, min(int(limit or 80), MAX_ITEMS))]

    def add(self, event: str = "joined") -> dict[str, Any] | None:
        kind = "session" if event == "session" else "joined"
        moment = _now()
        if kind == "joined" and self._too_soon(moment):
            return None
        item = {"at": _iso(moment), "event": kind}
        self.items.insert(0, item)
        self.items = self.items[:MAX_ITEMS]
        self._save()
        return item

    def _too_soon(self, moment: datetime) -> bool:
        if not self.items:
            return False
        last = self.items[0]
        if last.get("event") != "joined":
            return False
        previous = _parse(str(last.get("at") or ""))
        if previous is None:
            return False
        if previous.tzinfo is None:
            previous = previous.replace(tzinfo=timezone.utc)
        return (moment - previous).total_seconds() < VIEWER_DEBOUNCE_SEC

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("Could not read join log %s", self.path)
            return
        items = payload.get("items") if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            return
        cleaned: list[dict[str, Any]] = []
        for row in items:
            if not isinstance(row, dict):
                continue
            at = str(row.get("at") or "").strip()
            if not at:
                continue
            event = "session" if row.get("event") == "session" else "joined"
            cleaned.append({"at": at, "event": event})
        self.items = cleaned[:MAX_ITEMS]

    def _save(self) -> None:
        try:
            self.path.write_text(
                json.dumps({"items": self.items}, indent=2),
                encoding="utf-8",
            )
        except OSError:
            logger.warning("Could not write join log %s", self.path)
