"""Ensure only one Piano process is running."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

MUTEX_NAME = "Piano.SingleInstance"
ERROR_ALREADY_EXISTS = 183

_mutex_handle = None


def acquire_single_instance() -> bool:
    """Return False if another instance is already running."""
    global _mutex_handle
    if sys.platform != "win32":
        return True

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not handle:
        return True
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        return False
    _mutex_handle = handle
    return True


def warn_already_running(app_name: str) -> None:
    if sys.platform != "win32":
        return
    ctypes.windll.user32.MessageBoxW(
        None,
        f"{app_name} is already running.\nLook for it in the system tray.",
        app_name,
        0x40,
    )
