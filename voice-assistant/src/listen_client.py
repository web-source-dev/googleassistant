"""Read and set the web-panel listening switch on the backend."""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


def fetch_listen(backend_url: str) -> dict[str, Any] | None:
    try:
        with urlopen(f"{backend_url.rstrip('/')}/api/listen", timeout=4) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError) as exc:
        logger.debug("Listen status unavailable: %s", exc)
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def post_listen(backend_url: str, enabled: bool) -> dict[str, Any] | None:
    body = json.dumps({"enabled": bool(enabled)}).encode("utf-8")
    request = Request(
        f"{backend_url.rstrip('/')}/api/listen",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Content-Length": str(len(body))},
    )
    try:
        with urlopen(request, timeout=6) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError) as exc:
        logger.warning("Could not update listen switch: %s", exc)
        return None
    if not isinstance(payload, dict):
        return None
    return payload
