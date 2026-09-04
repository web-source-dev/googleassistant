"""Voice listener with a Turkish wake phrase and more reliable speech recognition."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

import speech_recognition as sr

from src.parser import parse_command, split_wake_command

logger = logging.getLogger(__name__)


class VoiceListener:
    def __init__(
        self,
        on_command: Callable[[str], None],
        on_status: Callable[[str], None] | None = None,
        on_heard: Callable[[str, bool], None] | None = None,
        on_clip: Callable[[sr.AudioData, str, bool], None] | None = None,
        energy_threshold: int = 150,
        pause_threshold: float = 1.0,
        speech_timeout: int = 8,
        phrase_time_limit: int = 12,
        wake_word: str = "asistan",
    ) -> None:
        self.on_command = on_command
        self.on_status = on_status or (lambda _: None)
        self.on_heard = on_heard or (lambda _t, _w: None)
        self.on_clip = on_clip or (lambda _a, _t, _w: None)
        self.speech_timeout = speech_timeout
        self.phrase_time_limit = phrase_time_limit
        self.wake_word = wake_word.strip() or "asistan"
        self._base_energy = max(80, min(int(energy_threshold), 350))

        self._recognizer = sr.Recognizer()
        self._recognizer.energy_threshold = self._base_energy
        self._recognizer.dynamic_energy_threshold = False
        self._recognizer.pause_threshold = max(0.8, float(pause_threshold))
        self._recognizer.non_speaking_duration = 0.5
        if hasattr(self._recognizer, "phrase_threshold"):
            self._recognizer.phrase_threshold = 0.2

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._paused = False
        self._listening = False

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive() and self._listening

    @property
    def is_paused(self) -> bool:
        return self._paused

    def start(self) -> None:
        if self.is_running:
            return
        if self._thread and self._thread.is_alive():
            self._stop_event.set()
            self._thread.join(timeout=5)
            if self._thread.is_alive():
                logger.warning("Cannot start listener; previous session is still stopping")
                return
        self._stop_event.clear()
        self._paused = False
        self._thread = threading.Thread(target=self._listen_loop, daemon=True, name="VoiceListener")
        self._thread.start()
        self._listening = True
        self.on_status(self._listening_status())

    def stop(self) -> None:
        if not self.is_running and not (self._thread and self._thread.is_alive()):
            self._listening = False
            return
        self._stop_event.set()
        self._listening = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        if self._thread and not self._thread.is_alive():
            self._thread = None
        self.on_status("Stopped")

    def pause(self) -> None:
        self._paused = True
        self.on_status("Paused")

    def resume(self) -> None:
        self._paused = False
        self.on_status(self._listening_status())

    def _listening_status(self) -> str:
        return f"'{self.wake_word}' bekleniyor..."

    def _listen_loop(self) -> None:
        try:
            mic = sr.Microphone(sample_rate=16000, chunk_size=1024)
        except OSError as exc:
            logger.error("Microphone error: %s", exc)
            self.on_status("Microphone not available")
            return

        with mic as source:
            try:
                self._recognizer.adjust_for_ambient_noise(source, duration=0.8)
            except Exception as exc:
                logger.warning("Ambient noise adjust failed: %s", exc)
            self._clamp_energy()
            logger.info("Energy threshold: %s", self._recognizer.energy_threshold)

            while not self._stop_event.is_set():
                if self._paused:
                    time.sleep(0.2)
                    continue

                audio = self._capture(source, wait_timeout=1.0)
                if audio is None:
                    continue

                text = self._best_transcript(audio) or ""
                wake, command = split_wake_command(text, self.wake_word) if text else (None, "")
                self._emit_clip(audio, text, wake is not None)
                if not text:
                    continue

                logger.info("Heard: %s", text)
                self.on_heard(text, wake is not None)

                if not wake:
                    continue

                if not command:
                    self.on_status("Komutu söyleyin...")
                    follow = self._capture(source, wait_timeout=6)
                    if follow is not None:
                        follow_text = self._best_transcript(follow, require_wake=False) or ""
                        self._emit_clip(follow, follow_text, False)
                        if follow_text:
                            logger.info("Follow-up: %s", follow_text)
                            self.on_heard(follow_text, False)
                            wake2, after = split_wake_command(follow_text, self.wake_word)
                            command = after if wake2 else follow_text

                if command:
                    self.on_command(command)
                self.on_status(self._listening_status())

    def _emit_clip(self, audio: sr.AudioData, transcript: str, wake: bool) -> None:
        try:
            self.on_clip(audio, transcript, wake)
        except Exception as exc:
            logger.warning("Voice clip callback failed: %s", exc)

    def _clamp_energy(self) -> None:
        self._recognizer.energy_threshold = max(80, min(self._recognizer.energy_threshold, 350))

    def _capture(self, source: sr.AudioSource, wait_timeout: float | None) -> sr.AudioData | None:
        try:
            return self._recognizer.listen(
                source,
                timeout=wait_timeout,
                phrase_time_limit=self.phrase_time_limit,
            )
        except sr.WaitTimeoutError:
            return None
        except OSError as exc:
            logger.error("Microphone error: %s", exc)
            self.on_status("Microphone not available")
            time.sleep(2)
            return None
        except Exception as exc:
            logger.error("Listen error: %s", exc)
            time.sleep(0.4)
            return None

    def _best_transcript(self, audio: sr.AudioData, require_wake: bool = True) -> str | None:
        candidates: list[str] = []
        candidates.extend(self._google_alternatives(audio, "tr-TR"))
        has_wake = any(split_wake_command(text, self.wake_word)[0] for text in candidates)
        if not candidates or (require_wake and not has_wake):
            candidates.extend(self._google_alternatives(audio, "en-US"))

        if not candidates:
            return None

        scored: list[tuple[int, int, str]] = []
        for text in candidates:
            wake, command = split_wake_command(text, self.wake_word)
            score = 0
            if wake:
                score += 2
                if command and parse_command(command).get("action") != "unknown":
                    score += 3
                elif command:
                    score += 1
            elif not require_wake and parse_command(text).get("action") != "unknown":
                score += 3
            scored.append((score, len(text), text))

        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return scored[0][2]

    def _google_alternatives(self, audio: sr.AudioData, language: str) -> list[str]:
        try:
            result: Any = self._recognizer.recognize_google(
                audio,
                language=language,
                show_all=True,
            )
        except sr.UnknownValueError:
            return []
        except sr.RequestError as exc:
            logger.error("Speech recognition API error (%s): %s", language, exc)
            self.on_status("Speech recognition unavailable")
            return []
        except Exception as exc:
            logger.warning("Recognition failed (%s): %s", language, exc)
            return []

        texts: list[str] = []
        if isinstance(result, str) and result.strip():
            texts.append(result.strip())
        elif isinstance(result, dict):
            blocks = result.get("alternative")
            if not blocks:
                inner = result.get("result") or []
                if inner and isinstance(inner, list):
                    blocks = inner[0].get("alternative") if isinstance(inner[0], dict) else []
            for item in blocks or []:
                if isinstance(item, dict):
                    transcript = str(item.get("transcript") or "").strip()
                    if transcript:
                        texts.append(transcript)
        seen: set[str] = set()
        unique: list[str] = []
        for text in texts:
            key = text.lower()
            if key not in seen:
                seen.add(key)
                unique.append(text)
        if unique:
            logger.info("STT %s: %s", language, unique[:5])
        return unique
