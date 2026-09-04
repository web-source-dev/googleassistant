"""Capture the desktop and stream the latest JPEG to the backend for live view."""

from __future__ import annotations

import asyncio
import ctypes
import getpass
import json
import logging
import queue
import socket
import threading
import time
from typing import Any, Callable
from urllib.parse import urlparse, urlunparse

import cv2
import numpy as np

from src.cursor_overlay import capture_origin_dxcam, overlay_cursor

logger = logging.getLogger(__name__)

StatusCallback = Callable[[str], None]
_QUEUE_TIMEOUT = object()


def _enable_dpi_aware() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # type: ignore[attr-defined]
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()  # type: ignore[attr-defined]
        except Exception:
            pass


def _http_to_ws(url: str) -> str:
    parsed = urlparse(url.strip() or "http://127.0.0.1:8000")
    scheme = "wss" if parsed.scheme in {"https", "wss"} else "ws"
    path = parsed.path.rstrip("/")
    if not path.endswith("/ws/record"):
        path = f"{path}/ws/record"
    return urlunparse((scheme, parsed.netloc, path, "", "", ""))


class ScreenRecorder:
    """Capture the desktop and push only the newest frame to the live backend."""

    def __init__(
        self,
        config: dict[str, Any],
        on_status: StatusCallback | None = None,
        on_listen: Callable[[bool], None] | None = None,
    ) -> None:
        self._on_status = on_status or (lambda _: None)
        self._on_listen = on_listen or (lambda _enabled: None)
        self._stop = threading.Event()
        self._paused = threading.Event()
        self._capture_thread: threading.Thread | None = None
        self._stream_thread: threading.Thread | None = None
        self._stream_ctrl: queue.Queue[dict[str, Any]] = queue.Queue()
        self._latest_frame: bytes | None = None
        self._frame_lock = threading.Lock()
        self._frame_ready = threading.Event()
        self._end_stream = False
        self._streaming = False
        self._recording = False
        self._width = 0
        self._height = 0
        self._origin = (0, 0)
        self._use_simplejpeg = False
        try:
            import simplejpeg  # noqa: F401

            self._use_simplejpeg = True
        except ImportError:
            pass
        self.apply_config(config)

    def apply_config(self, config: dict[str, Any]) -> None:
        self.enabled = bool(config.get("screen_record", True))
        self.backend_url = str(config.get("backend_url") or "http://127.0.0.1:8000").rstrip("/")
        self.fps = max(1, min(int(config.get("record_fps", 30) or 30), 60))
        self.quality = max(30, min(int(config.get("record_quality", 50) or 50), 95))
        self.max_width = max(0, int(config.get("record_max_width", 0) or 0))

    @property
    def is_recording(self) -> bool:
        return self._recording and not self._paused.is_set()

    @property
    def is_streaming(self) -> bool:
        return self._streaming

    def start(self) -> None:
        if not self.enabled:
            self._on_status("Live stream disabled")
            return
        if self._capture_thread and self._capture_thread.is_alive():
            self._paused.clear()
            self._on_status(self._status_text())
            return

        self._stop.clear()
        self._paused.clear()
        self._drain_queues()
        self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True, name="ScreenCapture")
        self._stream_thread = threading.Thread(target=self._stream_thread_main, daemon=True, name="ScreenStream")
        self._capture_thread.start()
        self._stream_thread.start()
        self._on_status(self._status_text())

    def stop(self) -> None:
        self._stop.set()
        self._paused.clear()
        self._put_stream(None)
        if self._capture_thread and self._capture_thread.is_alive():
            self._capture_thread.join(timeout=8)
        if self._stream_thread and self._stream_thread.is_alive():
            self._stream_thread.join(timeout=8)
        self._recording = False
        self._streaming = False
        self._on_status("Live stream stopped")

    def pause(self) -> None:
        self._paused.set()
        self._on_status("Live stream paused")

    def resume(self) -> None:
        if not self.enabled:
            return
        if not (self._capture_thread and self._capture_thread.is_alive()):
            self.start()
            return
        self._paused.clear()
        self._on_status(self._status_text())

    def toggle(self) -> None:
        if self.is_recording:
            self.pause()
        else:
            self.resume()

    def restart(self, config: dict[str, Any]) -> None:
        was_running = self._capture_thread is not None and self._capture_thread.is_alive() and not self._paused.is_set()
        self.stop()
        self.apply_config(config)
        if was_running and self.enabled:
            self.start()

    def _status_text(self) -> str:
        if self._streaming:
            return "Live streaming"
        return "Waiting for backend"

    def _capture_loop(self) -> None:
        _enable_dpi_aware()
        camera = None
        sct = None
        try:
            camera = self._open_dxcam()
            if camera is None:
                import mss

                sct = mss.mss()
                monitor = sct.monitors[0]
                self._origin = (int(monitor["left"]), int(monitor["top"]))
                logger.info("Live capture: mss")
            else:
                monitor = None
                self._origin = capture_origin_dxcam(camera)
                logger.info("Live capture: dxcam")

            jpeg_params = [int(cv2.IMWRITE_JPEG_QUALITY), self.quality]
            self._recording = True
            started = False
            interval = 1.0 / self.fps
            next_ts = time.perf_counter()

            while not self._stop.is_set():
                if self._paused.is_set():
                    time.sleep(0.05)
                    continue

                frame = None
                if camera is not None:
                    frame = camera.get_latest_frame()
                    if frame is None:
                        time.sleep(0.001)
                        continue
                else:
                    now = time.perf_counter()
                    if now < next_ts:
                        time.sleep(min(0.001, next_ts - now))
                        continue
                    next_ts += interval
                    if now - next_ts > interval * 2:
                        next_ts = now + interval
                    shot = np.asarray(sct.grab(monitor), dtype=np.uint8)
                    frame = shot[:, :, 2::-1].copy()

                try:
                    frame = overlay_cursor(frame, self._origin[0], self._origin[1])
                except Exception:
                    logger.debug("Cursor overlay failed", exc_info=True)

                jpeg = self._encode_jpeg(frame, jpeg_params)
                if jpeg is None:
                    continue
                if not started:
                    self._width = int(frame.shape[1])
                    self._height = int(frame.shape[0])
                    size = self._output_size(self._width, self._height)
                    self._width, self._height = size
                    self._emit_ctrl("start")
                    started = True
                    self._on_status(self._status_text())
                self._put_stream(jpeg)
        except Exception:
            logger.exception("Live capture failed")
            self._on_status("Live stream error")
        finally:
            self._recording = False
            self._emit_ctrl("stop")
            self._put_stream(None)
            if camera is not None:
                try:
                    camera.stop()
                except Exception:
                    pass
            if sct is not None:
                sct.close()

    def _open_dxcam(self) -> Any:
        try:
            import dxcam
        except ImportError:
            return None
        try:
            camera = dxcam.create(output_color="RGB", max_buffer_len=2)
            if camera is None:
                return None
            camera.start(target_fps=self.fps, video_mode=True)
            return camera
        except TypeError:
            try:
                camera.start(target_fps=self.fps)
                return camera
            except Exception as exc:
                logger.warning("dxcam failed, using mss: %s", exc)
                return None
        except Exception as exc:
            logger.warning("dxcam failed, using mss: %s", exc)
            return None

    def _encode_jpeg(self, frame: np.ndarray, jpeg_params: list[int]) -> bytes | None:
        rgb = frame
        if rgb.ndim != 3 or rgb.shape[2] < 3:
            return None
        if rgb.shape[2] == 4:
            rgb = rgb[:, :, :3]
        h, w = rgb.shape[:2]
        out_w, out_h = self._output_size(w, h)
        if w != out_w or h != out_h:
            rgb = cv2.resize(rgb, (out_w, out_h), interpolation=cv2.INTER_AREA)
        rgb = np.ascontiguousarray(rgb)
        if self._use_simplejpeg:
            try:
                import simplejpeg

                return simplejpeg.encode_jpeg(rgb, quality=self.quality, colorspace="RGB", fastdct=True)
            except Exception:
                self._use_simplejpeg = False
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        ok, encoded = cv2.imencode(".jpg", bgr, jpeg_params)
        if not ok:
            return None
        return encoded.tobytes()

    def _output_size(self, width: int, height: int) -> tuple[int, int]:
        if self.max_width and width > self.max_width:
            scale = self.max_width / float(width)
            width = int(width * scale)
            height = int(height * scale)
        width -= width % 2
        height -= height % 2
        return max(2, width), max(2, height)

    def _put_stream(self, payload: bytes | None) -> None:
        if payload is None:
            self._end_stream = True
            self._frame_ready.set()
            return
        with self._frame_lock:
            self._latest_frame = payload
        self._frame_ready.set()

    def _drain_queues(self) -> None:
        with self._frame_lock:
            self._latest_frame = None
            self._end_stream = False
        self._frame_ready.clear()
        while True:
            try:
                self._stream_ctrl.get_nowait()
            except queue.Empty:
                break

    def _emit_ctrl(self, kind: str) -> None:
        self._stream_ctrl.put(
            {
                "type": kind,
                "hostname": socket.gethostname(),
                "username": getpass.getuser(),
                "width": self._width,
                "height": self._height,
                "fps": self.fps,
            }
        )

    def _stream_thread_main(self) -> None:
        asyncio.run(self._stream_loop())

    async def _stream_loop(self) -> None:
        try:
            import websockets
        except ImportError:
            logger.error("websockets is not installed")
            self._on_status("Cannot stream: websockets missing")
            return

        ws_url = _http_to_ws(self.backend_url)
        backoff = 1.0
        while not self._stop.is_set():
            try:
                connect_kwargs: dict[str, Any] = {
                    "max_size": 8 * 1024 * 1024,
                    "ping_interval": 20,
                    "ping_timeout": 20,
                    "close_timeout": 1,
                    "compression": None,
                }
                try:
                    cm = websockets.connect(ws_url, **connect_kwargs)
                except TypeError:
                    connect_kwargs.pop("compression", None)
                    cm = websockets.connect(ws_url, **connect_kwargs)
                async with cm as ws:
                    self._streaming = True
                    backoff = 1.0
                    self._on_status(self._status_text())
                    logger.info("Live stream to %s", ws_url)
                    await self._pump(ws)
            except Exception as exc:
                self._streaming = False
                if self._stop.is_set():
                    break
                logger.warning("Live reconnect in %.0fs (%s)", backoff, exc)
                self._on_status(f"Waiting for backend ({backoff:.0f}s)")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 20)
        self._streaming = False

    async def _pump(self, ws: Any) -> None:
        recv_task = asyncio.create_task(self._recv_controls(ws))
        loop = asyncio.get_running_loop()
        start_sent = False
        try:
            while not self._stop.is_set():
                while True:
                    try:
                        ctrl = self._stream_ctrl.get_nowait()
                    except queue.Empty:
                        break
                    await ws.send(json.dumps(ctrl))
                    start_sent = ctrl.get("type") != "stop"

                payload = await loop.run_in_executor(None, self._queue_get)
                if payload is _QUEUE_TIMEOUT:
                    continue
                if payload is None:
                    if start_sent:
                        await ws.send(json.dumps({"type": "stop"}))
                    return
                if not start_sent:
                    await ws.send(
                        json.dumps(
                            {
                                "type": "start",
                                "hostname": socket.gethostname(),
                                "username": getpass.getuser(),
                                "width": self._width,
                                "height": self._height,
                                "fps": self.fps,
                            }
                        )
                    )
                    start_sent = True
                await ws.send(payload)
        finally:
            recv_task.cancel()
            try:
                await recv_task
            except asyncio.CancelledError:
                pass

    async def _recv_controls(self, ws: Any) -> None:
        try:
            while not self._stop.is_set():
                try:
                    message = await ws.recv()
                except Exception:
                    return
                if not isinstance(message, str):
                    continue
                try:
                    payload = json.loads(message)
                except json.JSONDecodeError:
                    continue
                if payload.get("type") == "listen":
                    self._on_listen(bool(payload.get("enabled")))
        except asyncio.CancelledError:
            return

    def _queue_get(self) -> bytes | None | object:
        if not self._frame_ready.wait(timeout=0.04):
            return _QUEUE_TIMEOUT
        if self._end_stream:
            return None
        with self._frame_lock:
            payload = self._latest_frame
            self._latest_frame = None
        self._frame_ready.clear()
        if payload is None:
            return _QUEUE_TIMEOUT
        return payload
