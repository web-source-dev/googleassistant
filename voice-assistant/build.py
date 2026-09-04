"""Build standalone Windows executable with PyInstaller."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ICON_PNG = ROOT / "assets" / "icon.png"
ICON_ICO = ROOT / "assets" / "icon.ico"
ICON = ICON_ICO if ICON_ICO.exists() else ICON_PNG
EXAMPLE_CONFIG = ROOT / "config.example.json"
ASSETS = ROOT / "assets"

HIDDEN_IMPORTS = [
    "customtkinter",
    "pystray",
    "PIL",
    "PIL.Image",
    "PIL.ImageDraw",
    "PIL.ImageTk",
    "speech_recognition",
    "pyaudio",
    "mss",
    "cv2",
    "numpy",
    "websockets",
    "dxcam",
    "simplejpeg",
    "appdirs",
    "pkg_resources",
    "setuptools",
    "packaging",
    "jaraco",
    "jaraco.text",
    "jaraco.context",
    "jaraco.functools",
    "more_itertools",
    "src.cursor_overlay",
    "src.updater",
    "src.version",
]


def _stop_running_app() -> None:
    subprocess.run(
        ["taskkill", "/F", "/IM", "Piano.exe", "/T"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def main() -> None:
    _stop_running_app()
    dist_exe = ROOT / "dist" / "Piano.exe"
    if dist_exe.is_file():
        try:
            dist_exe.unlink()
        except OSError as exc:
            raise SystemExit(
                f"Close Piano (and delete {dist_exe}) then build again.\n{exc}"
            ) from exc
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--windowed",
        "--name",
        "Piano",
        "--collect-all",
        "customtkinter",
        "--collect-all",
        "setuptools",
        "--copy-metadata",
        "setuptools",
        "--copy-metadata",
        "appdirs",
    ]

    for name in HIDDEN_IMPORTS:
        cmd.extend(["--hidden-import", name])

    if EXAMPLE_CONFIG.exists():
        cmd.extend(["--add-data", f"{EXAMPLE_CONFIG};."])
    else:
        print(f"Warning: {EXAMPLE_CONFIG.name} not found; skipping --add-data")

    if ASSETS.is_dir() and any(ASSETS.iterdir()):
        cmd.extend(["--add-data", f"{ASSETS};assets"])

    if ICON.exists():
        cmd.extend(["--icon", str(ICON)])

    cmd.append(str(ROOT / "main.py"))

    print("Running:", " ".join(cmd))
    subprocess.check_call(cmd, cwd=ROOT)
    print("\nBuild complete: dist/Piano/Piano.exe")


if __name__ == "__main__":
    main()
