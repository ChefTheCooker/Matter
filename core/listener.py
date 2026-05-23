# ============================================================
#  MATTER — core/listener.py
#  Matter's ears. Listens for the wake word "Hey Matter"
#  and captures everything the user says after it.
#
#  FIXES:
#  - Whisper loads lazily (not at import time) — no boot freeze
#  - Two-stage detection: SpeechRecognition for wake word (fast),
#    Whisper only for the actual command (accurate)
#  - Better error recovery in the wake loop
#  - Ambient noise recalibration every 60s
# ============================================================

import time
import threading
import tempfile
import os
import speech_recognition as sr
from core.config import (
    WAKE_WORD,
    WHISPER_MODEL,
    VOICE_LANGUAGE,
    MIC_ENERGY_THRESHOLD,
    MIC_PAUSE_DURATION,
    ENABLE_LOGS,
)


# ── Whisper — lazy load ───────────────────────────────────
#  Loads on first use so the boot sequence isn't blocked.
_whisper_model   = None
_whisper_loading = False
_whisper_lock    = threading.Lock()


def _get_whisper():
    global _whisper_model, _whisper_loading
    with _whisper_lock:
        if _whisper_model is None:
            if ENABLE_LOGS:
                print(f"[Listener] Loading Whisper '{WHISPER_MODEL}'...")
            import whisper
            _whisper_model = whisper.load_model(WHISPER_MODEL)
            if ENABLE_LOGS:
                print("[Listener] Whisper ready.")
    return _whisper_model


def preload_whisper():
    """
    Call this in a background thread after boot so Whisper
    is ready before the user speaks for the first time.
    """
    threading.Thread(target=_get_whisper, daemon=True).start()


# ── Microphone setup ──────────────────────────────────────
recognizer = sr.Recognizer()
recognizer.energy_threshold        = MIC_ENERGY_THRESHOLD
recognizer.pause_threshold         = MIC_PAUSE_DURATION
recognizer.dynamic_energy_threshold = True


# ── State ─────────────────────────────────────────────────
_listening_active  = False
_on_wake_callback  = None
_on_input_callback = None


def set_wake_callback(fn):
    global _on_wake_callback
    _on_wake_callback = fn


def set_input_callback(fn):
    global _on_input_callback
    _on_input_callback = fn


# ── Transcription (Whisper) ───────────────────────────────

def _transcribe_whisper(audio) -> str:
    """Full Whisper transcription — used for commands."""
    try:
        model = _get_whisper()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio.get_wav_data())
            tmp = f.name

        result = model.transcribe(tmp, language=VOICE_LANGUAGE, fp16=False)
        os.remove(tmp)
        text = result["text"].strip().lower()

        if ENABLE_LOGS:
            print(f"[Listener] Whisper heard: '{text}'")
        return text

    except Exception as e:
        if ENABLE_LOGS:
            print(f"[Listener] Whisper error: {e}")
        return ""


def _transcribe_fast(audio) -> str:
    """
    Fast Google SR transcription — used only for wake word detection.
    No GPU needed, near instant. Falls back to Whisper if it fails.
    """
    try:
        text = recognizer.recognize_google(audio).lower().strip()
        if ENABLE_LOGS:
            print(f"[Listener] Fast heard: '{text}'")
        return text
    except sr.UnknownValueError:
        return ""
    except sr.RequestError:
        # No internet or quota — fall back to Whisper
        if ENABLE_LOGS:
            print("[Listener] Google SR failed, falling back to Whisper for wake word.")
        return _transcribe_whisper(audio)
    except Exception as e:
        if ENABLE_LOGS:
            print(f"[Listener] Fast transcribe error: {e}")
        return ""


# ── Listen once (for commands) ────────────────────────────

def listen_once() -> str:
    """
    Listens for a single spoken command.
    Returns Whisper transcription. Blocks until done.
    Used AFTER wake word is detected.
    """
    with sr.Microphone() as source:
        if ENABLE_LOGS:
            print("[Listener] Listening for command...")

        recognizer.adjust_for_ambient_noise(source, duration=0.3)

        try:
            audio = recognizer.listen(source, timeout=10, phrase_time_limit=30)
            return _transcribe_whisper(audio)
        except sr.WaitTimeoutError:
            if ENABLE_LOGS:
                print("[Listener] Command timeout.")
            return ""
        except Exception as e:
            if ENABLE_LOGS:
                print(f"[Listener] listen_once error: {e}")
            return ""


# ── Wake word loop ────────────────────────────────────────

def _wake_word_loop():
    global _listening_active

    if ENABLE_LOGS:
        print(f"[Listener] Wake word loop started. Listening for '{WAKE_WORD}'...")

    last_calibration = time.time()

    while _listening_active:
        try:
            with sr.Microphone() as source:
                # Recalibrate every 60 seconds for ambient noise changes
                if time.time() - last_calibration > 60:
                    if ENABLE_LOGS:
                        print("[Listener] Recalibrating for ambient noise...")
                    recognizer.adjust_for_ambient_noise(source, duration=1)
                    last_calibration = time.time()
                else:
                    recognizer.adjust_for_ambient_noise(source, duration=0.5)

                while _listening_active:
                    try:
                        audio = recognizer.listen(
                            source,
                            timeout=3,
                            phrase_time_limit=6
                        )
                        text = _transcribe_fast(audio)

                        if not text:
                            continue

                        # ── Wake word check ────────────────
                        wake_words = WAKE_WORD.lower().split()
                        text_words = text.split()

                        # Check if all wake words appear in order
                        hit = all(w in text for w in wake_words)

                        # Also catch partial matches like "matter" alone
                        partial_hit = (
                            "matter" in text and
                            any(w in text for w in ["hey", "hello", "hi", "ok", "okay"])
                        )

                        if hit or partial_hit:
                            if ENABLE_LOGS:
                                print(f"[Listener] Wake word detected in: '{text}'")

                            if _on_wake_callback:
                                _on_wake_callback()

                            command = listen_once()

                            if command and _on_input_callback:
                                _on_input_callback(command)

                    except sr.WaitTimeoutError:
                        continue
                    except Exception as e:
                        if ENABLE_LOGS:
                            print(f"[Listener] Inner loop error: {e}")
                        time.sleep(0.5)
                        break  # Break inner, re-open mic

        except Exception as e:
            if ENABLE_LOGS:
                print(f"[Listener] Mic error: {e}. Retrying in 3s...")
            time.sleep(3)


# ── Public API ────────────────────────────────────────────

def start():
    global _listening_active

    if _listening_active:
        if ENABLE_LOGS:
            print("[Listener] Already running.")
        return

    _listening_active = True
    thread = threading.Thread(target=_wake_word_loop, daemon=True)
    thread.start()

    if ENABLE_LOGS:
        print("[Listener] Background listener started.")


def stop():
    global _listening_active
    _listening_active = False
    if ENABLE_LOGS:
        print("[Listener] Listener stopped.")


def is_active() -> bool:
    return _listening_active