# ============================================================
#  MATTER — core/speaker.py
#  Matter's voice. Converts text to speech and speaks aloud.
#  Supports pyttsx3 (free/offline) and ElevenLabs (premium).
# ============================================================

import threading
from typing import Optional
import pyttsx3
from core.config import (
    TTS_ENGINE,
    PYTTSX3_RATE,
    PYTTSX3_VOLUME,
    ELEVENLABS_API_KEY,
    ELEVENLABS_VOICE,
    ASSISTANT_NAME,
    ENABLE_LOGS,
)


# ── pyttsx3 engine setup ──────────────────────────────────
#  Typed as Optional so Pylance knows it starts as None
#  but becomes a pyttsx3.Engine after _init_pyttsx3() runs.
_engine: Optional[pyttsx3.Engine] = None


def _init_pyttsx3():
    global _engine
    _engine = pyttsx3.init()
    _engine.setProperty("rate",   PYTTSX3_RATE)
    _engine.setProperty("volume", PYTTSX3_VOLUME)

    voices = _engine.getProperty("voices") or []
    for voice in voices:
        if "english" in voice.name.lower():
            _engine.setProperty("voice", voice.id)
            break

    if ENABLE_LOGS:
        print(f"[Speaker] pyttsx3 ready.")


def _speak_elevenlabs(text: str):
    try:
        from elevenlabs import generate, play, set_api_key
        set_api_key(ELEVENLABS_API_KEY)
        audio = generate(text=text, voice= ELEVENLABS_VOICE)
        play(audio)
    except Exception as e:
        if ENABLE_LOGS:
            print(f"[Speaker] ElevenLabs error: {e}. Falling back to pyttsx3.")
        _speak_pyttsx3(text)


def _speak_pyttsx3(text: str):
    global _engine
    if _engine is None:
        _init_pyttsx3()
    assert _engine is not None   # tells Pylance: after init, this is never None
    try:
        _engine.say(text)
        _engine.runAndWait()
    except Exception as e:
        if ENABLE_LOGS:
            print(f"[Speaker] pyttsx3 error: {e}")


def say(text: str, blocking: bool = True):
    """
    Speaks the given text aloud using the configured TTS engine.

    Parameters:
      text     — what Matter will say
      blocking — if True, waits until speech is done before returning
                 if False, speaks in a background thread
    """
    if not text:
        return

    if ENABLE_LOGS:
        print(f"[Speaker] {ASSISTANT_NAME}: {text}")

    def _speak():
        if TTS_ENGINE == "elevenlabs":
            _speak_elevenlabs(text)
        else:
            _speak_pyttsx3(text)

    if blocking:
        _speak()
    else:
        thread = threading.Thread(target=_speak, daemon=True)
        thread.start()


def greet():
    say(f"Matter online. Good to see you, Sir. How can I help?")

def acknowledge():
    say("On it, Sir.")

def confirm(action: str) -> None:
    say(f"Sir, I am about to {action}. Shall I proceed?")

def error(message: Optional[str] = None):
    msg = message or "Sir, something went wrong. Please try again."
    say(msg)


if TTS_ENGINE == "pyttsx3":
    _init_pyttsx3()
