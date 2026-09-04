"""Upload captured microphone clips to the Harmony backend."""

from __future__ import annotations

import getpass
import logging
import queue
import socket
import threading
import uuid
from typing import Any
from urllib.request import Request, urlopen

import speech_recognition as sr

from src.config import DEFAULT_BACKEND_URL

logger = logging.getLogger(__name__)

MAX_QUEUE = 24
MAX_WAV_BYTES = 2 * 1024 * 1024
MIN_DURATION_MS = 180


def _clip_duration_ms(audio: sr.AudioData) -> int:
    width = max(1, int(audio.sample_width or 2))
    rate = max(1, int(audio.sample_rate or 16000))
    return int(1000 * (len(audio.frame_data) / width) / rate)


class AudioUploader:
    def __init__(self, config: dict[str, Any]) -> None:
        self._queue: queue.Queue[dict[str, Any] | None] = queue.Queue(maxsize=MAX_QUEUE)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.apply_config(config)

    def apply_config(self, config: dict[str, Any]) -> None:
        self.enabled = bool(config.get("send_voice", True))
        self.backend_url = str(config.get("backend_url") or DEFAULT_BACKEND_URL).rstrip("/")

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="VoiceUpload")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=4)

    def restart(self, config: dict[str, Any]) -> None:
        self.stop()
        self.apply_config(config)
        self.start()

    def enqueue(self, audio: Any, transcript: str, wake: bool) -> None:
        if not self.enabled:
            return
        transcript = (transcript or "").strip() or "Speaking"
        duration_ms = _clip_duration_ms(audio)
        if duration_ms < MIN_DURATION_MS:
            return
        try:
            wav = audio.get_wav_data()
        except Exception as exc:
            logger.warning("Could not encode voice clip: %s", exc)
            return
        if not wav or wav[:4] != b"RIFF" or len(wav) > MAX_WAV_BYTES:
            return

        item = {
            "wav": wav,
            "transcript": transcript[:2000],
            "wake": bool(wake),
            "duration_ms": duration_ms,
            "hostname": socket.gethostname(),
            "username": getpass.getuser(),
        }
        try:
            self._queue.put_nowait(item)
        except queue.Full:
            try:
                dropped = self._queue.get_nowait()
                if dropped is None:
                    self._queue.put_nowait(None)
                    return
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(item)
            except queue.Full:
                logger.warning("Voice upload queue full; dropped a clip")

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                item = self._queue.get(timeout=0.4)
            except queue.Empty:
                continue
            if item is None:
                return
            self._send_with_retry(item)

    def _send_with_retry(self, item: dict[str, Any]) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            try:
                self._post(item)
                return
            except Exception as exc:
                logger.warning("Voice upload retry in %.0fs (%s)", backoff, exc)
                if self._stop.wait(backoff):
                    return
                backoff = min(backoff * 2, 20)

    def _post(self, item: dict[str, Any]) -> None:
        boundary = uuid.uuid4().hex
        fields = {
            "transcript": item["transcript"],
            "wake": "true" if item["wake"] else "false",
            "hostname": str(item["hostname"]),
            "username": str(item["username"]),
        }
        body = _encode_multipart(boundary, fields, item["wav"])
        request = Request(
            f"{self.backend_url}/api/audio",
            data=body,
            method="POST",
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(len(body)),
            },
        )
        with urlopen(request, timeout=20) as response:
            response.read()
        logger.info(
            "Sent voice clip (%s ms, wake=%s): %s",
            item["duration_ms"],
            item["wake"],
            item["transcript"],
        )


def _encode_multipart(boundary: str, fields: dict[str, str], wav: bytes) -> bytes:
    chunks: list[bytes] = []
    marker = f"--{boundary}".encode("utf-8")
    for name, value in fields.items():
        chunks.extend(
            [
                marker,
                b"\r\n",
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
                value.encode("utf-8"),
                b"\r\n",
            ]
        )
    chunks.extend(
        [
            marker,
            b"\r\n",
            b'Content-Disposition: form-data; name="file"; filename="clip.wav"\r\n',
            b"Content-Type: audio/wav\r\n\r\n",
            wav,
            b"\r\n",
            f"--{boundary}--\r\n".encode("utf-8"),
        ]
    )
    return b"".join(chunks)
