"""
Piano — Desktop voice-activated assistant.

The microphone stays off until Voice assistant is enabled in the web panel.
"""

from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path

# Ensure project root is on path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import customtkinter as ctk

from src.audio_uploader import AudioUploader
from src.autostart import sync_autostart
from src.config import APP_NAME, DEFAULT_BACKEND_URL, load_config, save_config
from src.executor import CommandExecutor
from src.listen_client import fetch_listen, post_listen
from src.listener import VoiceListener
from src.parser import parse_command
from src.recorder import ScreenRecorder
from src.settings_window import SettingsWindow
from src.instance import acquire_single_instance, warn_already_running
from src.tray import TrayApp, apply_window_icon, ensure_app_icon
from src.updater import AppUpdater
from src.version import APP_VERSION

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def _enable_dpi_aware() -> None:
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # type: ignore[attr-defined]
    except Exception:
        try:
            import ctypes

            ctypes.windll.user32.SetProcessDPIAware()  # type: ignore[attr-defined]
        except Exception:
            pass


class AssistantApp:
    def __init__(self) -> None:
        self.config = load_config()
        self.status = "Voice assistant off"
        self._listening = False
        self._processing = False
        self._listen_stop = threading.Event()
        self._listen_lock = threading.Lock()

        ensure_app_icon()

        self.executor = CommandExecutor()

        self._tk_root = ctk.CTk()
        self._tk_root.withdraw()
        apply_window_icon(self._tk_root)

        self.listener = self._create_listener()

        self.settings = SettingsWindow(
            config=self.config,
            on_save=self._on_settings_saved,
            root=self._tk_root,
        )

        self.recorder = ScreenRecorder(
            self.config,
            on_status=self._on_record_status,
            on_listen=self._apply_listen,
        )
        self.voice_uploader = AudioUploader(self.config)

        self.tray = TrayApp(
            on_settings=self._open_settings,
            on_toggle_listening=self._toggle_listening,
            on_quit=self._quit,
            get_status=lambda: self.status,
            is_listening=lambda: self._listening and self.listener.is_running,
        )
        self.updater = AppUpdater(self._backend_url)

        sync_autostart(bool(self.config.get("autostart", False)))

    def _create_listener(self) -> VoiceListener:
        return VoiceListener(
            on_command=self._handle_command,
            on_status=self._set_status,
            on_heard=self._on_heard,
            on_clip=self._on_voice_clip,
            energy_threshold=int(self.config.get("energy_threshold", 150)),
            pause_threshold=float(self.config.get("pause_threshold", 1.0)),
            speech_timeout=int(self.config.get("speech_timeout", 8)),
            phrase_time_limit=int(self.config.get("phrase_time_limit", 12)),
            wake_word=str(self.config.get("wake_word", "asistan") or "asistan"),
        )

    def _on_heard(self, text: str, wake_detected: bool) -> None:
        logger.info("Heard%s: %s", " (wake)" if wake_detected else "", text)

    def _on_voice_clip(self, audio: object, transcript: str, wake: bool) -> None:
        self.voice_uploader.enqueue(audio, transcript, wake)

    def _set_status(self, status: str) -> None:
        self.status = status
        self.tray.update_status(status)
        logger.info("Status: %s", status)

    def _handle_command(self, text: str) -> None:
        self._process_command(text, source="voice")

    def _process_command(self, text: str, source: str = "voice") -> None:
        if self._processing:
            logger.info("Already processing a command, skipped")
            return

        logger.info("Command (%s): %s", source, text)
        self._processing = True

        threading.Thread(
            target=self._run_pipeline,
            args=(text,),
            daemon=True,
            name="CommandPipeline",
        ).start()

    def _run_pipeline(self, text: str) -> None:
        try:
            intent = parse_command(text)
            logger.info("Intent: %s", intent)

            if intent.get("action") == "unknown":
                logger.info("Ignored (no match): %s", text)
                self._set_status("Listening...")
                return

            success, message = self.executor.execute(intent)
            self._set_status(message if success else f"Failed: {message}")
        except Exception as exc:
            logger.exception("Pipeline error")
            self._set_status(f"Error: {exc}")
        finally:
            self._processing = False

    def _open_settings(self) -> None:
        self.settings.config = self.config.copy()
        self._tk_root.after(0, self.settings.show)

    def _on_settings_saved(self, new_config: dict) -> None:
        self.config.update(new_config)
        save_config(self.config)
        sync_autostart(bool(new_config.get("autostart", False)))

        with self._listen_lock:
            if self._listening:
                self.listener.stop()
                self.listener = self._create_listener()
                self.listener.start()
            else:
                self.listener.stop()
                self.listener = self._create_listener()

        self.recorder.restart(self.config)
        self.voice_uploader.restart(self.config)

        self._set_status("Settings saved")

    def _backend_url(self) -> str:
        return str(self.config.get("backend_url") or DEFAULT_BACKEND_URL).rstrip("/")

    def _apply_listen(self, enabled: bool) -> None:
        enabled = bool(enabled)
        with self._listen_lock:
            running = self.listener.is_running and not self.listener.is_paused
            if enabled and running:
                self._listening = True
                return
            if not enabled and not self.listener.is_running:
                self._listening = False
                return

            if enabled:
                if not self.listener.is_running:
                    self.listener.start()
                else:
                    self.listener.resume()
                self._listening = True
                logger.info("Microphone on — listening for commands")
            else:
                self.listener.stop()
                self._listening = False
                self._set_status("Voice assistant off")
                logger.info("Microphone off")

    def _poll_listen(self) -> None:
        while not self._listen_stop.is_set():
            payload = fetch_listen(self._backend_url())
            if payload is None:
                if self._listening:
                    self._apply_listen(False)
            else:
                self._apply_listen(bool(payload.get("enabled")))
            if self._listen_stop.wait(1.5):
                break

    def _toggle_listening(self) -> None:
        wanted = not (self._listening and self.listener.is_running and not self.listener.is_paused)
        payload = post_listen(self._backend_url(), wanted)
        if payload is not None:
            self._apply_listen(bool(payload.get("enabled")))

    def _on_record_status(self, status: str) -> None:
        logger.info("Record: %s", status)

    def _quit(self) -> None:
        logger.info("Shutting down")
        self._listen_stop.set()
        self.updater.stop()
        self.recorder.stop()
        self.voice_uploader.stop()
        with self._listen_lock:
            self.listener.stop()
        self.tray.stop()
        self._tk_root.after(0, self._tk_root.destroy)

    def run(self) -> None:
        logger.info("Starting %s %s (microphone off until enabled in the web panel)", APP_NAME, APP_VERSION)
        self._listen_stop.clear()
        threading.Thread(target=self._poll_listen, daemon=True, name="ListenPoll").start()
        self.recorder.start()
        self.voice_uploader.start()
        self.tray.run()
        self.updater.start()
        self._tk_root.mainloop()


def main() -> None:
    if not acquire_single_instance():
        warn_already_running(APP_NAME)
        return
    _enable_dpi_aware()
    app = AssistantApp()
    app.run()


if __name__ == "__main__":
    main()
