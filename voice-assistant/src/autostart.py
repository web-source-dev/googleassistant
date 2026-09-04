"""Windows autostart via registry."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_REGISTRY_NAME = "GoogleAssistant"
LEGACY_REGISTRY_NAMES = ("HarmonyVoiceAssistant",)


def get_launch_command() -> str:
    """Build the command used to start the app on boot."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'

    main_script = Path(__file__).resolve().parent.parent / "main.py"
    python = sys.executable
    return f'"{python}" "{main_script}"'


def is_autostart_enabled() -> bool:
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
            for name in (APP_REGISTRY_NAME, *LEGACY_REGISTRY_NAMES):
                try:
                    winreg.QueryValueEx(key, name)
                    return True
                except OSError:
                    continue
        return False
    except OSError:
        return False


def enable_autostart() -> bool:
    try:
        import winreg

        command = get_launch_command()
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, APP_REGISTRY_NAME, 0, winreg.REG_SZ, command)
            for legacy in LEGACY_REGISTRY_NAMES:
                try:
                    winreg.DeleteValue(key, legacy)
                except OSError:
                    pass
        logger.info("Autostart enabled: %s", command)
        return True
    except OSError as exc:
        logger.error("Failed to enable autostart: %s", exc)
        return False


def disable_autostart() -> bool:
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            for name in (APP_REGISTRY_NAME, *LEGACY_REGISTRY_NAMES):
                try:
                    winreg.DeleteValue(key, name)
                except OSError:
                    pass
        logger.info("Autostart disabled")
        return True
    except OSError as exc:
        logger.error("Failed to disable autostart: %s", exc)
        return False


def sync_autostart(enabled: bool) -> None:
    if enabled:
        enable_autostart()
    else:
        disable_autostart()
