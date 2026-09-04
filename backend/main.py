"""Google Assistant live-stream backend.

Relays JPEG frames from the voice assistant to the web viewer.
Spoken microphone clips are saved and listed for playback.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from audio_store import MAX_WAV_BYTES, AudioStore
from hub import LiveHub
from app_updates import installer_file, latest_payload

ROOT = Path(__file__).resolve().parent
FRONTEND_DIR = ROOT.parent / "frontend"
STATIC_DIR = ROOT / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("harmony.backend")

app = FastAPI(title="Google Assistant", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

live_hub = LiveHub()
audio_store = AudioStore(ROOT / "data" / "audio")


class ListenRequest(BaseModel):
    enabled: bool


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _session_meta(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "hostname": str(payload.get("hostname") or "pc"),
        "username": str(payload.get("username") or "user"),
        "width": int(payload.get("width") or 0),
        "height": int(payload.get("height") or 0),
        "fps": float(payload.get("fps") or 0),
        "started_at": _iso(),
        "viewers": live_hub.viewer_count(),
    }


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "streaming": live_hub.session is not None,
        "viewers": live_hub.viewer_count(),
        "voice_clips": audio_store.count(),
        "listening": live_hub.listening_enabled,
        "assistant_connected": live_hub.assistant_connected(),
    }


@app.get("/api/live")
def live_status() -> dict[str, Any]:
    session = live_hub.session
    return {
        "live": session is not None,
        "viewers": live_hub.viewer_count(),
        "has_frame": live_hub.latest_jpeg is not None,
        "session": session,
    }


@app.get("/api/live/frame")
def live_frame() -> Response:
    if not live_hub.latest_jpeg:
        raise HTTPException(status_code=404, detail="No live frame")
    return Response(
        content=live_hub.latest_jpeg,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/listen")
def get_listen() -> dict[str, Any]:
    return live_hub.listen_payload()


@app.post("/api/listen")
async def set_listen(body: ListenRequest) -> dict[str, Any]:
    payload = await live_hub.set_listening(body.enabled)
    logger.info(
        "Voice assistant %s (desktop %s)",
        "on" if payload["enabled"] else "off",
        "connected" if payload["assistant_connected"] else "offline",
    )
    return payload


@app.get("/api/app/latest")
def app_latest() -> dict[str, Any]:
    return latest_payload()


@app.get("/api/app/download")
def app_download() -> FileResponse:
    return installer_file()


@app.get("/api/audio")
def list_audio(limit: int = 50) -> dict[str, Any]:
    return {"items": audio_store.list(limit)}


@app.get("/api/audio/{clip_id}")
def get_audio(clip_id: str) -> FileResponse:
    path = audio_store.wav_path(clip_id)
    if path is None:
        raise HTTPException(status_code=404, detail="Voice clip not found")
    return FileResponse(
        path,
        media_type="audio/wav",
        filename=f"{clip_id}.wav",
        headers={"Cache-Control": "private, max-age=86400"},
    )


@app.post("/api/audio")
async def upload_audio(
    file: UploadFile = File(...),
    transcript: str = Form(""),
    wake: str = Form("false"),
    hostname: str = Form(""),
    username: str = Form(""),
) -> dict[str, Any]:
    wav = await file.read()
    if len(wav) > MAX_WAV_BYTES:
        raise HTTPException(status_code=413, detail="Audio clip is too large")
    wake_flag = str(wake).strip().lower() in {"1", "true", "yes", "on"}
    try:
        item = audio_store.save(
            wav,
            transcript=transcript,
            wake=wake_flag,
            hostname=hostname,
            username=username,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await live_hub.push_voice(item)
    return item


@app.websocket("/ws/record")
async def record_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    await live_hub.set_source(websocket)
    logger.info("Live source connected from %s", websocket.client)
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            text = message.get("text")
            data = message.get("bytes")
            if text:
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError:
                    continue
                kind = str(payload.get("type") or "")
                if kind in {"start", "segment"}:
                    await live_hub.set_session(_session_meta(payload))
                    await websocket.send_json({"type": "ack"})
                elif kind == "stop":
                    await live_hub.set_session(None)
                    await websocket.send_json({"type": "stopped"})
            elif data:
                await live_hub.push_frame(data)
    except WebSocketDisconnect:
        logger.info("Live source disconnected")
    except Exception:
        logger.exception("Live source error")
    finally:
        await live_hub.clear_source(websocket)
        await live_hub.set_session(None)


@app.websocket("/ws/live")
async def live_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    await live_hub.add(websocket)
    logger.info("Viewer connected (%s)", live_hub.viewer_count())
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
    except WebSocketDisconnect:
        pass
    finally:
        live_hub.remove(websocket)
        logger.info("Viewer left (%s)", live_hub.viewer_count())


@app.get("/")
def dashboard() -> FileResponse:
    frontend_index = FRONTEND_DIR / "index.html"
    if frontend_index.exists():
        return FileResponse(frontend_index)
    index = STATIC_DIR / "index.html"
    if not index.exists():
        raise HTTPException(status_code=404, detail="Live page missing")
    return FileResponse(index)


if FRONTEND_DIR.exists():
    css_dir = FRONTEND_DIR / "css"
    js_dir = FRONTEND_DIR / "js"
    assets_dir = FRONTEND_DIR / "assets"
    if css_dir.exists():
        app.mount("/css", StaticFiles(directory=css_dir), name="frontend-css")
    if js_dir.exists():
        app.mount("/js", StaticFiles(directory=js_dir), name="frontend-js")
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="frontend-assets")

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000)
