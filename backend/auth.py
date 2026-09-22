"""Password gate for the web viewer.

The frontend must POST the password to /api/auth/login to receive a bearer
token, which it then sends on every request. The password itself lives in
the backend environment (APP_PASSWORD), never in the frontend.
"""

from __future__ import annotations

import os
import secrets
import time
from pathlib import Path
from typing import Optional

from fastapi import Header, HTTPException, Query, WebSocket, WebSocketException, status

ROOT = Path(__file__).resolve().parent
TOKEN_TTL_SECONDS = 30 * 24 * 60 * 60  # 30 days


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv(ROOT / ".env")

APP_PASSWORD = os.environ.get("APP_PASSWORD", "")

_tokens: dict[str, float] = {}


def _prune() -> None:
    now = time.time()
    for token in [t for t, expires in _tokens.items() if expires < now]:
        _tokens.pop(token, None)


def _valid(token: Optional[str]) -> bool:
    if not token:
        return False
    expires = _tokens.get(token)
    if expires is None:
        return False
    if expires < time.time():
        _tokens.pop(token, None)
        return False
    return True


def login(password: str) -> str:
    if not APP_PASSWORD:
        raise HTTPException(status_code=503, detail="APP_PASSWORD is not configured on the server")
    if not secrets.compare_digest(str(password or ""), APP_PASSWORD):
        raise HTTPException(status_code=401, detail="Incorrect password")
    _prune()
    token = secrets.token_urlsafe(32)
    _tokens[token] = time.time() + TOKEN_TTL_SECONDS
    return token


def require_auth(
    authorization: Optional[str] = Header(default=None),
    token: Optional[str] = Query(default=None),
) -> None:
    """FastAPI dependency for HTTP routes.

    Accepts either an `Authorization: Bearer <token>` header (used by fetch())
    or a `?token=` query param (used by <audio>/<img> tags that can't set
    custom headers).
    """
    bearer = None
    if authorization and authorization.lower().startswith("bearer "):
        bearer = authorization[7:].strip()
    if not (_valid(bearer) or _valid(token)):
        raise HTTPException(status_code=401, detail="Not authenticated")


async def require_auth_ws(websocket: WebSocket, token: Optional[str] = Query(default=None)) -> None:
    """FastAPI dependency for WebSocket routes (browsers can't set headers on WS)."""
    if not _valid(token):
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Not authenticated")
