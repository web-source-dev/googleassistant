"""Settings window UI."""

from __future__ import annotations

import threading
from typing import Callable

import customtkinter as ctk

from src.config import APP_NAME, DEFAULT_BACKEND_URL
from src.version import APP_VERSION


class SettingsWindow:
    def __init__(
        self,
        config: dict,
        on_save: Callable[[dict], None],
        root: ctk.CTk | None = None,
    ) -> None:
        self.config = config.copy()
        self.on_save = on_save
        self._owns_root = root is None
        self.root = root or ctk.CTk()
        self._window: ctk.CTkToplevel | ctk.CTk | None = None

    def show(self) -> None:
        if self._window is not None and self._window.winfo_exists():
            self._window.lift()
            self._window.focus_force()
            return

        if self._owns_root:
            self._window = self.root
            self._window.title(f"{APP_NAME} — Settings")
            self._window.geometry("540x680")
            self._window.resizable(False, False)
        else:
            self._window = ctk.CTkToplevel(self.root)
            self._window.title(f"{APP_NAME} — Settings")
            self._window.geometry("540x680")
            self._window.resizable(False, False)

        self._build_ui()
        if not self._owns_root:
            self._window.grab_set()
            try:
                from src.tray import apply_window_icon

                apply_window_icon(self._window)
            except Exception:
                pass

    def _build_ui(self) -> None:
        assert self._window is not None
        win = self._window

        for widget in win.winfo_children():
            widget.destroy()

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        frame = ctk.CTkScrollableFrame(win, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=24, pady=24)

        ctk.CTkLabel(
            frame,
            text=APP_NAME,
            font=ctk.CTkFont(size=22, weight="bold"),
        ).pack(anchor="w", pady=(0, 4))

        ctk.CTkLabel(
            frame,
            text=f"Version {APP_VERSION}",
            text_color="gray70",
        ).pack(anchor="w", pady=(0, 4))

        ctk.CTkLabel(
            frame,
            text="Türkçe uyandırma kelimesi ve mikrofon ayarları.",
            text_color="gray70",
        ).pack(anchor="w", pady=(0, 20))

        ctk.CTkLabel(frame, text="Uyandırma kelimesi (Türkçe)", anchor="w").pack(fill="x")
        self.wake_word_entry = ctk.CTkEntry(frame, placeholder_text="asistan")
        self.wake_word_entry.pack(fill="x", pady=(4, 12))
        self.wake_word_entry.insert(0, self.config.get("wake_word", "asistan") or "asistan")

        # Autostart
        self.autostart_var = ctk.BooleanVar(value=self.config.get("autostart", False))
        ctk.CTkCheckBox(
            frame,
            text="Start with Windows",
            variable=self.autostart_var,
        ).pack(anchor="w", pady=(0, 16))

        ctk.CTkLabel(frame, text="Screen recording", font=ctk.CTkFont(size=16, weight="bold")).pack(
            anchor="w", pady=(8, 8)
        )
        rec = ctk.CTkFrame(frame, fg_color=("gray90", "gray17"))
        rec.pack(fill="x", pady=(0, 12))

        self.record_var = ctk.BooleanVar(value=self.config.get("screen_record", True))
        ctk.CTkCheckBox(
            rec,
            text="Stream the desktop live to the web page",
            variable=self.record_var,
        ).pack(anchor="w", padx=12, pady=(12, 8))

        self.send_voice_var = ctk.BooleanVar(value=self.config.get("send_voice", True))
        ctk.CTkCheckBox(
            rec,
            text="Send spoken audio clips to the backend",
            variable=self.send_voice_var,
        ).pack(anchor="w", padx=12, pady=(0, 8))

        self.backend_entry = self._labeled_entry(
            rec, "Backend URL", self.config.get("backend_url", DEFAULT_BACKEND_URL)
        )
        self.fps_entry = self._labeled_entry(rec, "FPS", self.config.get("record_fps", 30))
        self.quality_entry = self._labeled_entry(rec, "JPEG quality (30-95)", self.config.get("record_quality", 50))
        self.max_width_entry = self._labeled_entry(
            rec, "Max width (0 = full screen)", self.config.get("record_max_width", 0)
        )
        ctk.CTkLabel(rec, text="").pack(pady=(0, 4))

        # Advanced
        ctk.CTkLabel(frame, text="Advanced", font=ctk.CTkFont(size=16, weight="bold")).pack(
            anchor="w", pady=(8, 8)
        )

        adv = ctk.CTkFrame(frame, fg_color=("gray90", "gray17"))
        adv.pack(fill="x", pady=(0, 12))

        self.energy_entry = self._labeled_entry(adv, "Energy Threshold", self.config.get("energy_threshold", 300))
        self.pause_entry = self._labeled_entry(adv, "Pause Threshold (sec)", self.config.get("pause_threshold", 0.8))
        self.timeout_entry = self._labeled_entry(adv, "Speech Timeout (sec)", self.config.get("speech_timeout", 5))
        self.phrase_entry = self._labeled_entry(adv, "Phrase Limit (sec)", self.config.get("phrase_time_limit", 10))

        # Status label
        self.status_label = ctk.CTkLabel(frame, text="", text_color="gray60")
        self.status_label.pack(anchor="w", pady=(8, 0))

        # Buttons
        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(16, 0))

        ctk.CTkButton(btn_frame, text="Save", command=self._save, width=120).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            btn_frame,
            text="Cancel",
            command=self._close,
            width=120,
            fg_color="gray40",
            hover_color="gray30",
        ).pack(side="left")

        # Usage hint
        hint = ctk.CTkTextbox(frame, height=100, fg_color=("gray92", "gray20"))
        hint.pack(fill="x", pady=(20, 0))
        hint.insert(
            "1.0",
            'Kullanım:\n'
            '1. "asistan" de\n'
            '2. Aynı cümlede komutu söyle: "asistan YouTube aç"\n'
            '   veya "asistan" deyip ardından "Discord"\n'
            'e-Devlet, e-okul, EBA, Trendyol, MEB de çalışır.',
        )
        hint.configure(state="disabled")

    def _labeled_entry(self, parent: ctk.CTkFrame, label: str, value) -> ctk.CTkEntry:
        ctk.CTkLabel(parent, text=label, anchor="w").pack(fill="x", padx=12, pady=(8, 0))
        entry = ctk.CTkEntry(parent)
        entry.pack(fill="x", padx=12, pady=(4, 4))
        entry.insert(0, str(value))
        return entry

    def _save(self) -> None:
        try:
            new_config = {
                "require_wake_word": True,
                "wake_word": self.wake_word_entry.get().strip().lower() or "asistan",
                "autostart": self.autostart_var.get(),
                "energy_threshold": int(self.energy_entry.get()),
                "pause_threshold": float(self.pause_entry.get()),
                "speech_timeout": int(self.timeout_entry.get()),
                "phrase_time_limit": int(self.phrase_entry.get()),
                "screen_record": self.record_var.get(),
                "send_voice": self.send_voice_var.get(),
                "backend_url": self.backend_entry.get().strip() or DEFAULT_BACKEND_URL,
                "record_fps": int(self.fps_entry.get()),
                "record_quality": int(self.quality_entry.get()),
                "record_max_width": int(self.max_width_entry.get()),
            }
        except ValueError:
            self.status_label.configure(text="Invalid numeric value in advanced settings.", text_color="#ef4444")
            return

        self.config.update(new_config)
        self.on_save(new_config)
        self.status_label.configure(text="Settings saved.", text_color="#22c55e")

        if not self._owns_root:
            threading.Timer(0.8, self._close).start()

    def _close(self) -> None:
        if self._window and not self._owns_root:
            self._window.destroy()
            self._window = None
        elif self._owns_root:
            self.root.withdraw()

    def run(self) -> None:
        self.root.mainloop()
