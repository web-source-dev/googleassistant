"""Download and silently install a newer Google Assistant build from the backend."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable
from urllib.error import URLError
from urllib.request import Request, urlopen

from src.config import get_app_dir
from src.version import APP_VERSION, is_newer

logger = logging.getLogger(__name__)

TASK_NAME = "GoogleAssistantSilentUpdate"
START_DELAY_SEC = 8
CHECK_INTERVAL_SEC = 30 * 60
NotifyFn = Callable[[str], None]
CREATE_NO_WINDOW = 0x08000000


class AppUpdater:
    def __init__(self, backend_url: Callable[[], str], notify: NotifyFn) -> None:
        self._backend_url = backend_url
        self._notify = notify
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._told_current = False

    def start(self) -> None:
        if not getattr(sys, "frozen", False):
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="AppUpdater")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        self._report_pending_result()
        if self._stop.wait(START_DELAY_SEC):
            return
        while not self._stop.is_set():
            try:
                if self._check_once():
                    return
            except Exception:
                logger.exception("Update check failed")
            if self._stop.wait(CHECK_INTERVAL_SEC):
                return

    def _report_pending_result(self) -> None:
        pending = _read_json(_pending_path())
        if not pending:
            return
        self._told_current = True
        try:
            _pending_path().unlink(missing_ok=True)
        except OSError:
            pass
        wanted = str(pending.get("to") or "")
        previous = str(pending.get("from") or "")
        if wanted and not is_newer(wanted, APP_VERSION):
            self._notify(f"Google Assistant updated to {APP_VERSION}")
            return
        if previous and previous == APP_VERSION:
            self._notify(f"Google Assistant was not updated (still {APP_VERSION})")
            return
        self._notify(f"Google Assistant is running version {APP_VERSION}")

    def _check_once(self) -> bool:
        latest = _fetch_latest(self._backend_url())
        if latest is None:
            if not self._told_current:
                self._notify("Could not check for Google Assistant updates")
                self._told_current = True
            return False
        remote = str(latest.get("version") or "")
        if not latest.get("available") or not remote or not is_newer(remote, APP_VERSION):
            if not self._told_current:
                self._notify(f"Google Assistant is up to date ({APP_VERSION})")
                self._told_current = True
            return False

        self._notify(f"Downloading Google Assistant {remote}…")
        installer = _download_installer(self._backend_url(), str(latest.get("url") or "/api/app/download"))
        if installer is None:
            self._notify("Google Assistant update download failed")
            return False
        staged = _stage_installer(installer)
        _write_json(
            _pending_path(),
            {"from": APP_VERSION, "to": remote, "at": time.time()},
        )
        self._notify(f"Installing Google Assistant {remote}…")
        if not _start_silent_install():
            self._notify("Google Assistant update could not start")
            try:
                _pending_path().unlink(missing_ok=True)
            except OSError:
                pass
            return False
        time.sleep(1.2)
        os._exit(0)


def _updates_dir() -> Path:
    path = get_app_dir() / "updates"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _pending_path() -> Path:
    return get_app_dir() / "pending-update.json"


def _programdata_dir() -> Path:
    return Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "GoogleAssistant"


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _fetch_latest(backend_url: str) -> dict[str, Any] | None:
    try:
        with urlopen(f"{backend_url.rstrip('/')}/api/app/latest", timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError) as exc:
        logger.debug("Update manifest unavailable: %s", exc)
        return None
    return payload if isinstance(payload, dict) else None


def _download_installer(backend_url: str, url: str) -> Path | None:
    if url.startswith("/"):
        url = f"{backend_url.rstrip('/')}{url}"
    dest = _updates_dir() / "GoogleAssistant.exe"
    tmp = dest.with_suffix(".part")
    try:
        request = Request(url, headers={"User-Agent": f"GoogleAssistant/{APP_VERSION}"})
        with urlopen(request, timeout=120) as response, tmp.open("wb") as handle:
            while True:
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
        tmp.replace(dest)
        if dest.stat().st_size < 1024:
            dest.unlink(missing_ok=True)
            return None
        return dest
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        logger.warning("Update download failed: %s", exc)
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        return None


def _stage_installer(installer: Path) -> Path:
    staged = _programdata_dir() / "pending.exe"
    try:
        staged.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(installer, staged)
        return staged
    except OSError as exc:
        logger.warning("Could not stage installer in ProgramData: %s", exc)
        return installer


def _start_silent_install() -> bool:
    if _run_scheduled_task():
        return True
    helper = _programdata_dir() / "silent-update.cmd"
    if not helper.is_file():
        helper = Path(sys.executable).resolve().parent / "silent-update.cmd"
    if not helper.is_file():
        logger.warning("silent-update.cmd is missing")
        return False
    try:
        subprocess.Popen(
            ["cmd.exe", "/c", str(helper)],
            cwd=str(helper.parent),
            close_fds=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW | 0x00000008 | 0x00000200,
        )
        return True
    except OSError as exc:
        logger.warning("Could not start silent update: %s", exc)
        return False


def _run_scheduled_task() -> bool:
    try:
        completed = subprocess.run(
            ["schtasks", "/Run", "/TN", TASK_NAME],
            capture_output=True,
            text=True,
            timeout=20,
            creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.debug("Scheduled update task not run: %s", exc)
        return False
    if completed.returncode != 0:
        logger.debug("Scheduled update task failed: %s", completed.stderr.strip())
        return False
    return True
