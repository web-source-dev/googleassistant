"""Command execution: launch apps, open URLs, web search."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import webbrowser
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from src.config import KNOWN_TARGETS

logger = logging.getLogger(__name__)


class CommandExecutor:
    def execute(self, intent: dict[str, Any]) -> tuple[bool, str]:
        action = intent.get("action", "unknown")
        target = str(intent.get("target", "")).strip().lower()
        url = intent.get("url")
        speak = intent.get("speak", "")

        if action == "open":
            success, message = self._open(target, url)
        elif action == "search":
            success, message = self._search(target)
        elif action == "close":
            success, message = self._close(target)
        else:
            return False, speak or "Sorry, I did not understand that."

        return success, message or speak

    def _open(self, target: str, url: str | None) -> tuple[bool, str]:
        if not target and not url:
            return False, "No target specified."

        normalized = self._normalize(target)
        known = KNOWN_TARGETS.get(normalized, {})

        app_names = list(known.get("apps") or [])
        if not app_names and not known.get("url") and not url:
            app_names = [normalized]

        for name in app_names:
            if self._launch_app(name):
                return True, f"Opened {target or name}"

        known_url = url or known.get("url")
        if known_url:
            webbrowser.open(known_url)
            return True, f"Opened {target or known_url}"

        if target.startswith("http"):
            webbrowser.open(target)
            return True, f"Opened {target}"

        return False, f"Could not find or open '{target}'."

    def _search(self, query: str) -> tuple[bool, str]:
        if not query:
            return False, "No search query provided."
        url = f"https://www.google.com.tr/search?q={quote_plus(query)}&hl=tr"
        webbrowser.open(url)
        return True, f"Searching for {query}"

    def _close(self, target: str) -> tuple[bool, str]:
        if not target:
            return False, "No app specified to close."
        try:
            subprocess.run(
                ["taskkill", "/IM", f"{target}.exe", "/F"],
                capture_output=True,
                check=False,
            )
            return True, f"Attempted to close {target}"
        except OSError as exc:
            logger.error("Close failed: %s", exc)
            return False, f"Could not close {target}"

    def _launch_app(self, name: str) -> bool:
        if name.startswith("ms-settings:"):
            try:
                os.startfile(name)  # type: ignore[attr-defined]
                return True
            except OSError:
                return False

        exe = shutil.which(name)
        if exe:
            try:
                subprocess.Popen(
                    [exe],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                return True
            except OSError:
                pass

        for path in self._common_paths(name):
            if path.exists():
                try:
                    os.startfile(str(path))  # type: ignore[attr-defined]
                    return True
                except OSError:
                    pass

        builtins = {
            "notepad",
            "calc",
            "mspaint",
            "explorer",
            "cmd",
            "powershell",
            "taskmgr",
            "winword",
            "excel",
            "powerpnt",
        }
        if name not in builtins:
            return False

        try:
            subprocess.Popen(
                ["cmd", "/c", "start", "", name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            return True
        except OSError:
            return False

    def _common_paths(self, name: str) -> list[Path]:
        local = Path(os.environ.get("LOCALAPPDATA", ""))
        program_files = Path(os.environ.get("ProgramFiles", "C:\\Program Files"))
        program_files_x86 = Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"))

        candidates: dict[str, list[Path]] = {
            "chrome": [
                program_files / "Google/Chrome/Application/chrome.exe",
                program_files_x86 / "Google/Chrome/Application/chrome.exe",
            ],
            "msedge": [
                program_files / "Microsoft/Edge/Application/msedge.exe",
                program_files_x86 / "Microsoft/Edge/Application/msedge.exe",
            ],
            "firefox": [
                program_files / "Mozilla Firefox/firefox.exe",
                program_files_x86 / "Mozilla Firefox/firefox.exe",
            ],
            "spotify": [local / "Microsoft/WindowsApps/Spotify.exe"],
            "discord": [
                local / "Discord/Update.exe",
                local / "Discord/Discord.exe",
            ],
            "code": [local / "Programs/Microsoft VS Code/Code.exe"],
            "cursor": [local / "Programs/cursor/Cursor.exe"],
            "steam": [program_files_x86 / "Steam/steam.exe"],
            "slack": [local / "slack/slack.exe"],
            "whatsapp": [local / "WhatsApp/WhatsApp.exe"],
            "telegram": [
                local / "Telegram Desktop/Telegram.exe",
                program_files / "Telegram Desktop/Telegram.exe",
            ],
            "zoom": [
                program_files / "Zoom/bin/Zoom.exe",
                local / "Zoom/bin/Zoom.exe",
            ],
        }
        return candidates.get(name, [])

    def _normalize(self, target: str) -> str:
        return target.lower().strip().replace(" ", "")
