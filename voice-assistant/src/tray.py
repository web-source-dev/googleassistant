"""System tray integration."""

from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw
import pystray
from pystray import MenuItem as Item

from src.config import APP_NAME, get_assets_dir

logger = logging.getLogger(__name__)


def create_default_icon(size: int = 64) -> Image.Image:
    """Generate a simple piano-key tray icon if the logo files are missing."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad = max(2, size // 16)
    draw.rounded_rectangle(
        [pad, pad, size - pad, size - pad],
        radius=size // 5,
        fill=(30, 27, 75, 255),
    )
    kb_top = int(size * 0.38)
    kb_bot = int(size * 0.82)
    kb_left = int(size * 0.18)
    kb_right = int(size * 0.82)
    keys = 5
    width = (kb_right - kb_left) / keys
    for i in range(keys):
        x0 = kb_left + i * width
        draw.rectangle(
            [x0, kb_top, x0 + width - 1, kb_bot],
            fill=(248, 250, 252, 255),
            outline=(30, 27, 75, 255),
        )
    for i in (0, 1, 3):
        x = kb_left + (i + 0.72) * width
        draw.rectangle(
            [x, kb_top, x + width * 0.48, kb_top + (kb_bot - kb_top) * 0.58],
            fill=(15, 23, 42, 255),
        )
    return img


def load_icon() -> Image.Image:
    assets = get_assets_dir()
    for name in ("icon.png", "icon.ico"):
        path = assets / name
        if path.exists():
            try:
                return Image.open(path).convert("RGBA")
            except OSError as exc:
                logger.warning("Could not load icon %s: %s", path, exc)
    return create_default_icon()


def ensure_app_icon() -> Path:
    """Keep the bundled logo. Never overwrite a custom icon.png."""
    assets = get_assets_dir()
    png = assets / "icon.png"
    if getattr(sys, "frozen", False):
        return png if png.exists() else assets / "icon.ico"
    assets.mkdir(parents=True, exist_ok=True)
    if not png.exists():
        create_default_icon(256).save(png, "PNG")
    _ensure_ico(png)
    return png


def _ensure_ico(png: Path) -> Path | None:
    ico = png.with_suffix(".ico")
    try:
        if ico.exists() and ico.stat().st_mtime >= png.stat().st_mtime:
            return ico
        image = Image.open(png).convert("RGBA")
        image.save(
            ico,
            format="ICO",
            sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
        )
        return ico
    except OSError as exc:
        logger.warning("Could not write icon.ico: %s", exc)
        return None


def apply_window_icon(window: object) -> None:
    png = ensure_app_icon()
    ico = png.with_suffix(".ico")
    try:
        if ico.exists() and hasattr(window, "iconbitmap"):
            window.iconbitmap(str(ico))
    except Exception as exc:
        logger.warning("Could not set window iconbitmap: %s", exc)
    try:
        from PIL import ImageTk

        photo = ImageTk.PhotoImage(Image.open(png).convert("RGBA"))
        window._harmony_icon_photo = photo  # type: ignore[attr-defined]
        if hasattr(window, "iconphoto"):
            window.iconphoto(True, photo)
    except Exception as exc:
        logger.warning("Could not set window icon: %s", exc)


class TrayApp:
    def __init__(
        self,
        on_settings: Callable[[], None],
        on_toggle_listening: Callable[[], None],
        on_quit: Callable[[], None],
        get_status: Callable[[], str],
        is_listening: Callable[[], bool],
    ) -> None:
        self.on_settings = on_settings
        self.on_toggle_listening = on_toggle_listening
        self.on_quit = on_quit
        self.get_status = get_status
        self.is_listening = is_listening
        self._icon: pystray.Icon | None = None
        self._thread: threading.Thread | None = None

    def _build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            Item(lambda _: self.get_status(), None, enabled=False),
            pystray.Menu.SEPARATOR,
            Item(
                lambda item: "Pause Listening" if self.is_listening() else "Start Listening",
                self._handle_toggle,
            ),
            Item("Settings", self._handle_settings),
            pystray.Menu.SEPARATOR,
            Item("Quit", self._handle_quit),
        )

    def _handle_toggle(self, icon: pystray.Icon, item: Item) -> None:
        self.on_toggle_listening()

    def _handle_settings(self, icon: pystray.Icon, item: Item) -> None:
        self.on_settings()

    def _handle_quit(self, icon: pystray.Icon, item: Item) -> None:
        self.on_quit()
        if self._icon:
            self._icon.stop()

    def update_status(self, status: str) -> None:
        if self._icon:
            self._icon.title = f"{APP_NAME} — {status}"

    def run(self) -> None:
        self._icon = pystray.Icon(
            APP_NAME,
            load_icon(),
            APP_NAME,
            menu=self._build_menu(),
        )
        self._thread = threading.Thread(target=self._icon.run, daemon=False, name="TrayIcon")
        self._thread.start()

    def stop(self) -> None:
        if self._icon:
            self._icon.stop()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)


def save_default_icon() -> Path:
    """Compatibility wrapper — does not replace an existing logo."""
    return ensure_app_icon()
