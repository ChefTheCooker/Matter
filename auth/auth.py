# ============================================================
#  MATTER — auth/auth.py
#  Handles user authorization. Before Matter does anything
#  significant, it asks for confirmation. Always.
# ============================================================

import time
import threading
from core.config import (
    AUTH_TIMEOUT,
    ASSISTANT_NAME,
    ENABLE_LOGS,
)


# ── State ─────────────────────────────────────────────────
_pending_response = None        # 'yes', 'no', or None
_awaiting_response = False      # Is Matter waiting for auth?


def _reset():
    global _pending_response, _awaiting_response
    _pending_response  = None
    _awaiting_response = False


# ── Core Auth ─────────────────────────────────────────────

def request(action: str, speaker, listener) -> bool:
    """
    Asks the user to confirm an action before executing it.
    Waits up to AUTH_TIMEOUT seconds for a yes/no response.

    Parameters:
      action   — description of what Matter is about to do
      speaker  — the speaker module (to speak the confirmation prompt)
      listener — the listener module (to capture the user's response)

    Returns True if user confirms, False if denied or timed out.
    """
    global _pending_response, _awaiting_response

    _reset()
    _awaiting_response = True

    # Ask the user
    speaker.say(f"Sir, I am about to {action}. Do you want me to proceed?")

    if ENABLE_LOGS:
        print(f"[Auth] Waiting for confirmation: '{action}'")

    # Listen for yes/no
    start_time = time.time()

    while time.time() - start_time < AUTH_TIMEOUT:
        response = listener.listen_once().lower().strip()

        if not response:
            continue

        if any(word in response for word in ["yes", "yeah", "do it", "proceed", "go ahead", "sure", "confirm"]):
            _reset()
            if ENABLE_LOGS:
                print("[Auth] Authorized.")
            speaker.say("Understood, Sir. Proceeding.")
            return True

        if any(word in response for word in ["no", "nope", "stop", "cancel", "don't", "abort"]):
            _reset()
            if ENABLE_LOGS:
                print("[Auth] Denied by user.")
            speaker.say("Understood, Sir. Cancelling.")
            return False

    # Timed out
    _reset()
    if ENABLE_LOGS:
        print("[Auth] Authorization timed out.")
    speaker.say("Sir, I received no response. Cancelling for safety.")
    return False


def is_awaiting() -> bool:
    """
    Returns True if Matter is currently waiting for auth confirmation.
    """
    return _awaiting_response


def silent_check(user_input: str) -> bool:
    """
    Quick inline check — returns True if the user's input
    sounds like a confirmation. Used for fast yes/no checks
    without a full auth cycle.
    """
    text = user_input.lower().strip()
    return any(word in text for word in [
        "yes", "yeah", "do it", "proceed",
        "go ahead", "sure", "confirm", "yep", "absolutely"
    ])


def silent_deny(user_input: str) -> bool:
    """
    Quick inline check — returns True if the user's input
    sounds like a denial.
    """
    text = user_input.lower().strip()
    return any(word in text for word in [
        "no", "nope", "stop", "cancel",
        "don't", "abort", "negative", "never"
    ])