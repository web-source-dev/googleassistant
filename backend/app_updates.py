"""Serve the latest desktop installer for silent updates."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from fastapi.responses import FileResponse

UPDATES_DIR = Path(__file__).resolve().parent / "data" / "updates"
INSTALLER_NAME = "Piano.exe"


def latest_payload() -> dict[str, Any]:
    manifest = _read_manifest()
    version = str((manifest or {}).get("version") or "")
    filename = str((manifest or {}).get("filename") or INSTALLER_NAME)
    installer = _installer_path(filename)
    exists = installer.is_file() and installer.stat().st_size > 1024
    return {
        "available": bool(version) and exists,
        "version": version or None,
        "filename": filename,
        "size": installer.stat().st_size if exists else 0,
        "url": "/api/app/download",
    }


def installer_file() -> FileResponse:
    payload = latest_payload()
    if not payload["available"]:
        raise HTTPException(status_code=404, detail="No app update is published")
    path = _installer_path(str(payload["filename"]))
    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=INSTALLER_NAME,
        headers={"Cache-Control": "no-store"},
    )


def _read_manifest() -> dict[str, Any] | None:
    path = UPDATES_DIR / "latest.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _installer_path(filename: str) -> Path:
    name = Path(filename).name
    if name not in {INSTALLER_NAME, "Piano.exe", "GoogleAssistant.exe", "GoogleAssistantSetup.exe"}:
        name = INSTALLER_NAME
    return UPDATES_DIR / name
