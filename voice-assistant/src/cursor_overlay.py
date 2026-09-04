"""Draw the real Windows mouse pointer onto an RGB screenshot."""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes
from typing import Any

import numpy as np

CURSOR_SHOWING = 0x00000001
DI_NORMAL = 0x0003
BI_RGB = 0

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class CURSORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint),
        ("flags", ctypes.c_uint),
        ("hCursor", wintypes.HANDLE),
        ("ptScreenPos", POINT),
    ]


class ICONINFO(ctypes.Structure):
    _fields_ = [
        ("fIcon", wintypes.BOOL),
        ("xHotspot", wintypes.DWORD),
        ("yHotspot", wintypes.DWORD),
        ("hbmMask", wintypes.HBITMAP),
        ("hbmColor", wintypes.HBITMAP),
    ]


class BITMAP(ctypes.Structure):
    _fields_ = [
        ("bmType", ctypes.c_long),
        ("bmWidth", ctypes.c_long),
        ("bmHeight", ctypes.c_long),
        ("bmWidthBytes", ctypes.c_long),
        ("bmPlanes", ctypes.c_ushort),
        ("bmBitsPixel", ctypes.c_ushort),
        ("bmBits", ctypes.c_void_p),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


user32.GetCursorInfo.argtypes = [ctypes.POINTER(CURSORINFO)]
user32.GetCursorInfo.restype = wintypes.BOOL
user32.GetIconInfo.argtypes = [wintypes.HICON, ctypes.POINTER(ICONINFO)]
user32.GetIconInfo.restype = wintypes.BOOL
user32.DrawIconEx.argtypes = [
    wintypes.HDC,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HICON,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.UINT,
    wintypes.HANDLE,
    wintypes.UINT,
]
user32.DrawIconEx.restype = wintypes.BOOL
user32.GetDC.argtypes = [wintypes.HWND]
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.ReleaseDC.restype = ctypes.c_int
gdi32.GetObjectW.argtypes = [wintypes.HGDIOBJ, ctypes.c_int, ctypes.c_void_p]
gdi32.GetObjectW.restype = ctypes.c_int
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateDIBSection.argtypes = [
    wintypes.HDC,
    ctypes.POINTER(BITMAPINFO),
    wintypes.UINT,
    ctypes.POINTER(ctypes.c_void_p),
    wintypes.HANDLE,
    wintypes.DWORD,
]
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteObject.restype = wintypes.BOOL
gdi32.DeleteDC.argtypes = [wintypes.HDC]
gdi32.DeleteDC.restype = wintypes.BOOL

_sprite_cache: dict[str, Any] = {"handle": 0, "rgba": None, "hotspot": (0, 0), "at": 0.0}


def capture_origin_dxcam(camera: Any) -> tuple[int, int]:
    try:
        coords = camera._output.desc.DesktopCoordinates  # type: ignore[attr-defined]
        return int(coords.left), int(coords.top)
    except Exception:
        return 0, 0


def overlay_cursor(frame: np.ndarray, origin_x: int, origin_y: int) -> np.ndarray:
    if frame.ndim != 3 or frame.shape[2] < 3:
        return frame
    info = CURSORINFO()
    info.cbSize = ctypes.sizeof(CURSORINFO)
    if not user32.GetCursorInfo(ctypes.byref(info)):
        return frame
    if not (info.flags & CURSOR_SHOWING) or not info.hCursor:
        return frame

    sprite, hotspot = _cursor_sprite(int(info.hCursor))
    if sprite is None:
        sprite, hotspot = _fallback_pointer()

    x = int(info.ptScreenPos.x) - int(origin_x) - int(hotspot[0])
    y = int(info.ptScreenPos.y) - int(origin_y) - int(hotspot[1])
    out = np.array(frame, copy=True)
    _blend(out, sprite, x, y)
    return out


def _cursor_sprite(handle: int) -> tuple[np.ndarray | None, tuple[int, int]]:
    now = time.monotonic()
    if _sprite_cache["handle"] == handle and _sprite_cache["rgba"] is not None and now - _sprite_cache["at"] < 1.0:
        return _sprite_cache["rgba"], _sprite_cache["hotspot"]

    icon = ICONINFO()
    if not user32.GetIconInfo(handle, ctypes.byref(icon)):
        return None, (0, 0)
    try:
        width, height = _icon_size(icon)
        rgba = _icon_to_rgba(handle, width, height)
        hotspot = (int(icon.xHotspot), int(icon.yHotspot))
    finally:
        if icon.hbmColor:
            gdi32.DeleteObject(icon.hbmColor)
        if icon.hbmMask:
            gdi32.DeleteObject(icon.hbmMask)

    if rgba is None:
        return None, (0, 0)
    _sprite_cache.update({"handle": handle, "rgba": rgba, "hotspot": hotspot, "at": now})
    return rgba, hotspot


def _icon_size(icon: ICONINFO) -> tuple[int, int]:
    bitmap = BITMAP()
    handle = icon.hbmColor or icon.hbmMask
    if handle and gdi32.GetObjectW(handle, ctypes.sizeof(bitmap), ctypes.byref(bitmap)):
        height = abs(int(bitmap.bmHeight))
        if not icon.hbmColor and height > 1:
            height //= 2
        return max(16, int(bitmap.bmWidth)), max(16, height)
    return 32, 32


def _icon_to_rgba(hicon: int, width: int, height: int) -> np.ndarray | None:
    hdc_screen = user32.GetDC(None)
    if not hdc_screen:
        return None
    hdc = gdi32.CreateCompatibleDC(hdc_screen)
    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = width
    bmi.bmiHeader.biHeight = -height
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = BI_RGB
    bits = ctypes.c_void_p()
    hbitmap = gdi32.CreateDIBSection(hdc, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
    if not hbitmap or not bits:
        if hbitmap:
            gdi32.DeleteObject(hbitmap)
        if hdc:
            gdi32.DeleteDC(hdc)
        user32.ReleaseDC(None, hdc_screen)
        return None
    old = gdi32.SelectObject(hdc, hbitmap)
    ctypes.memset(bits, 0, width * height * 4)
    user32.DrawIconEx(hdc, 0, 0, hicon, width, height, 0, None, DI_NORMAL)
    buf = ctypes.string_at(bits, width * height * 4)
    bgra = np.frombuffer(buf, dtype=np.uint8).reshape((height, width, 4)).copy()
    gdi32.SelectObject(hdc, old)
    gdi32.DeleteObject(hbitmap)
    gdi32.DeleteDC(hdc)
    user32.ReleaseDC(None, hdc_screen)
    rgba = bgra[:, :, [2, 1, 0, 3]]
    if int(rgba[:, :, 3].max()) == 0:
        opaque = np.any(rgba[:, :, :3] > 0, axis=2)
        rgba[:, :, 3] = np.where(opaque, 255, 0).astype(np.uint8)
    return rgba


def _fallback_pointer() -> tuple[np.ndarray, tuple[int, int]]:
    sprite = np.zeros((20, 12, 4), dtype=np.uint8)
    polygon = [(0, 0), (0, 16), (4, 12), (7, 19), (9, 18), (6, 11), (11, 11)]
    mask = np.zeros((20, 12), dtype=bool)
    for y in range(20):
        for x in range(12):
            if _point_in_polygon(x, y, polygon):
                mask[y, x] = True
    sprite[mask] = (255, 255, 255, 255)
    padded = np.pad(mask.astype(np.uint8), 1)
    edge = mask & (
        (padded[:-2, 1:-1] == 0)
        | (padded[2:, 1:-1] == 0)
        | (padded[1:-1, :-2] == 0)
        | (padded[1:-1, 2:] == 0)
    )
    sprite[edge] = (15, 15, 15, 255)
    return sprite, (1, 1)


def _point_in_polygon(x: int, y: int, polygon: list[tuple[int, int]]) -> bool:
    inside = False
    j = len(polygon) - 1
    for i, (xi, yi) in enumerate(polygon):
        xj, yj = polygon[j]
        intersect = ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / ((yj - yi) or 1) + xi)
        if intersect:
            inside = not inside
        j = i
    return inside


def _blend(dst: np.ndarray, sprite: np.ndarray, x: int, y: int) -> None:
    ch, cw = sprite.shape[:2]
    h, w = dst.shape[:2]
    x0 = max(0, x)
    y0 = max(0, y)
    x1 = min(w, x + cw)
    y1 = min(h, y + ch)
    if x0 >= x1 or y0 >= y1:
        return
    patch = sprite[y0 - y : y1 - y, x0 - x : x1 - x]
    alpha = patch[:, :, 3:4].astype(np.float32) / 255.0
    if float(alpha.max()) == 0:
        return
    rgb = patch[:, :, :3].astype(np.float32)
    roi = dst[y0:y1, x0:x1, :3].astype(np.float32)
    dst[y0:y1, x0:x1, :3] = (rgb * alpha + roi * (1.0 - alpha)).astype(np.uint8)
