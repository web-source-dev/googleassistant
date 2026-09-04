"""Fan-out the latest live JPEG to every browser viewer with no backlog."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketState

logger = logging.getLogger(__name__)


class LiveHub:
    def __init__(self) -> None:
        self.viewers: set[WebSocket] = set()
        self.latest_jpeg: bytes | None = None
        self.session: dict[str, Any] | None = None
        self.source: WebSocket | None = None
        self.listening_enabled = False
        self._busy: set[WebSocket] = set()
        self._generation = 0

    def viewer_count(self) -> int:
        return len(self.viewers)

    def assistant_connected(self) -> bool:
        return self.source is not None and self.source.client_state == WebSocketState.CONNECTED

    def listen_payload(self) -> dict[str, Any]:
        return {
            "type": "listen",
            "enabled": self.listening_enabled,
            "assistant_connected": self.assistant_connected(),
        }

    async def add(self, websocket: WebSocket) -> None:
        self.viewers.add(websocket)
        if self.session is not None:
            await self._safe_json(websocket, {"type": "session", **self.session})
        else:
            await self._safe_json(websocket, {"type": "idle"})
        await self._safe_json(websocket, self.listen_payload())
        if self.latest_jpeg:
            await self._safe_bytes(websocket, self.latest_jpeg)

    def remove(self, websocket: WebSocket) -> None:
        self.viewers.discard(websocket)
        self._busy.discard(websocket)

    async def set_session(self, meta: dict[str, Any] | None) -> None:
        self.session = meta
        if meta is None:
            self.latest_jpeg = None
            self._generation += 1
            await self._broadcast_json({"type": "idle"})
            return
        await self._broadcast_json({"type": "session", **meta})

    async def set_source(self, websocket: WebSocket) -> None:
        self.source = websocket
        await self._send_listen_to_source()
        await self._broadcast_json(self.listen_payload())

    async def clear_source(self, websocket: WebSocket | None = None) -> None:
        if websocket is not None and self.source is not websocket:
            return
        self.source = None
        await self._broadcast_json(self.listen_payload())

    async def set_listening(self, enabled: bool) -> dict[str, Any]:
        self.listening_enabled = bool(enabled)
        await self._send_listen_to_source()
        payload = self.listen_payload()
        await self._broadcast_json(payload)
        return payload

    async def _send_listen_to_source(self) -> None:
        if self.source is None:
            return
        await self._safe_json(self.source, self.listen_payload())

    async def push_voice(self, clip: dict[str, Any]) -> None:
        await self._broadcast_json({**clip, "type": "voice"})

    async def push_frame(self, data: bytes) -> None:
        if not data:
            return
        self.latest_jpeg = data
        self._generation += 1
        for websocket in list(self.viewers):
            if websocket in self._busy:
                continue
            self._busy.add(websocket)
            asyncio.create_task(self._pump_latest(websocket))

    async def _pump_latest(self, websocket: WebSocket) -> None:
        try:
            while websocket in self.viewers:
                gen = self._generation
                frame = self.latest_jpeg
                if not frame:
                    return
                await self._safe_bytes(websocket, frame)
                if self._generation == gen:
                    return
        finally:
            self._busy.discard(websocket)

    async def _broadcast_json(self, payload: dict[str, Any]) -> None:
        for websocket in list(self.viewers):
            await self._safe_json(websocket, payload)

    async def _safe_json(self, websocket: WebSocket, payload: dict[str, Any]) -> None:
        if websocket.client_state != WebSocketState.CONNECTED:
            self.remove(websocket)
            if self.source is websocket:
                self.source = None
            return
        try:
            await websocket.send_json(payload)
        except Exception:
            self.remove(websocket)
            if self.source is websocket:
                self.source = None

    async def _safe_bytes(self, websocket: WebSocket, data: bytes) -> None:
        if websocket.client_state != WebSocketState.CONNECTED:
            self.remove(websocket)
            return
        try:
            await websocket.send_bytes(data)
        except Exception:
            self.remove(websocket)
