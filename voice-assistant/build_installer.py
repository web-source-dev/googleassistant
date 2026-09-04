"""Build the app folder, then compile the Windows setup wizard."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ISS = ROOT / "installer" / "google-assistant.iss"
RELEASE = ROOT / "release"
UPDATES = ROOT.parent / "backend" / "data" / "updates"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.version import APP_VERSION, file_version


def _find_iscc() -> Path | None:
    which = shutil.which("ISCC.exe")
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    local_app = os.environ.get("LOCALAPPDATA", "")
    candidates = [
        Path(which) if which else None,
        Path(local_app) / "Programs" / "Inno Setup 6" / "ISCC.exe",
        Path(pf86) / "Inno Setup 6" / "ISCC.exe",
        Path(pf) / "Inno Setup 6" / "ISCC.exe",
    ]
    for candidate in candidates:
        if candidate and candidate.exists():
            return candidate
    return None


def _install_inno_setup() -> Path | None:
    winget = shutil.which("winget")
    if not winget:
        return None
    print("Installing Inno Setup (needed for the installer wizard)...")
    subprocess.check_call(
        [
            winget,
            "install",
            "--id",
            "JRSoftware.InnoSetup",
            "-e",
            "--accept-package-agreements",
            "--accept-source-agreements",
            "--disable-interactivity",
        ]
    )
    return _find_iscc()


def _iscc() -> Path:
    iscc = _find_iscc() or _install_inno_setup()
    if iscc is None:
        raise SystemExit(
            "Inno Setup compiler (ISCC.exe) was not found. "
            "Install Inno Setup 6, then run: python build_installer.py"
        )
    return iscc


def set_app_version(version: str) -> None:
    path = ROOT / "src" / "version.py"
    text = path.read_text(encoding="utf-8")
    updated, count = re.subn(
        r'APP_VERSION = ["\'].*?["\']',
        f'APP_VERSION = "{version}"',
        text,
        count=1,
    )
    if count != 1:
        raise SystemExit(f"Could not set APP_VERSION to {version} in {path}")
    path.write_text(updated, encoding="utf-8")


def _compile_and_publish(version: str, make_latest: bool) -> Path:
    payload = ROOT / "dist" / "GoogleAssistant" / "GoogleAssistant.exe"
    subprocess.check_call([sys.executable, str(ROOT / "build.py")], cwd=ROOT)
    if not payload.exists():
        raise SystemExit(f"Missing app payload: {payload}")

    iscc = _iscc()
    RELEASE.mkdir(parents=True, exist_ok=True)
    print("Compiling installer", version, "with", iscc)
    subprocess.check_call(
        [
            str(iscc),
            f"/DMyAppVersion={version}",
            f"/DMyVersionInfoVersion={file_version(version)}",
            str(ISS),
        ],
        cwd=ROOT,
    )
    setup = RELEASE / "GoogleAssistant.exe"
    if not setup.exists():
        raise SystemExit("Installer compile finished but GoogleAssistant.exe was not created")
    _publish_update(setup, version, make_latest=make_latest)
    return setup


def _publish_update(setup: Path, version: str, make_latest: bool = True) -> None:
    UPDATES.mkdir(parents=True, exist_ok=True)
    versioned = UPDATES / f"GoogleAssistant-{version}.exe"
    shutil.copy2(setup, versioned)
    if make_latest:
        shutil.copy2(setup, UPDATES / "GoogleAssistant.exe")
        (UPDATES / "latest.json").write_text(
            json.dumps({"version": version, "filename": "GoogleAssistant.exe"}, indent=2),
            encoding="utf-8",
        )
    print(f"Saved {versioned}")


def _build_pair(low: str, high: str) -> None:
    print(f"Building install-this-first {low}, then latest {high}")
    set_app_version(low)
    _compile_and_publish(low, make_latest=False)
    set_app_version(high)
    setup = _compile_and_publish(high, make_latest=True)
    print(f"\nInstall first: {UPDATES / f'GoogleAssistant-{low}.exe'}")
    print(f"Auto-update target: {UPDATES / 'GoogleAssistant.exe'} ({high})")
    print(f"Also at: {setup}")


def main() -> None:
    args = sys.argv[1:]
    if "--pair" in args:
        idx = args.index("--pair")
        if len(args) < idx + 3:
            raise SystemExit("Usage: python build_installer.py --pair 34.5.06 34.5.07")
        _build_pair(args[idx + 1], args[idx + 2])
        return

    skip_build = "--skip-build" in args
    payload = ROOT / "dist" / "GoogleAssistant" / "GoogleAssistant.exe"
    if not skip_build or not payload.exists():
        subprocess.check_call([sys.executable, str(ROOT / "build.py")], cwd=ROOT)
    if not payload.exists():
        raise SystemExit(f"Missing app payload: {payload}")

    iscc = _iscc()
    RELEASE.mkdir(parents=True, exist_ok=True)
    print("Compiling installer with", iscc)
    subprocess.check_call(
        [
            str(iscc),
            f"/DMyAppVersion={APP_VERSION}",
            f"/DMyVersionInfoVersion={file_version(APP_VERSION)}",
            str(ISS),
        ],
        cwd=ROOT,
    )
    setup = RELEASE / "GoogleAssistant.exe"
    if not setup.exists():
        raise SystemExit("Installer compile finished but GoogleAssistant.exe was not created")
    _publish_update(setup, APP_VERSION, make_latest=True)
    print(f"\nInstaller ready: {setup}")
    print(f"Published for silent updates: {UPDATES / 'GoogleAssistant.exe'}")


if __name__ == "__main__":
    main()
