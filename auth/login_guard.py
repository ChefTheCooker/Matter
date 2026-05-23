# ============================================================
#  MATTER — auth/login_guard.py
#  The gatekeeper. Blocks any sensitive action from running
#  without passing through authorization first.
#  Every dangerous task MUST go through this file.
# ============================================================

from core.config import ENABLE_LOGS


# ── Sensitive intent list ─────────────────────────────────
#  Any intent in this list requires explicit user confirmation
#  before engine.py is allowed to execute it.

GUARDED_INTENTS = [
    "shutdown",
    "restart",
    "sleep",
    "close_app",
    "create_file",
    "open_file",
    "set_alarm",
    "set_reminder",
    "search_web",
    "open_url",
    "stream_mode",
    "coding_mode",
    "clear_memory",
    "exit_matter",
    "smart_home_control",   # For the smart home feature
]

# ── Intents that are always safe — no confirmation needed ──
SAFE_INTENTS = [
    "get_time",
    "get_date",
    "get_weather",
    "get_news",
    "who_are_you",
    "thanks",
    "wikipedia",
    "volume_up",
    "volume_down",
    "mute",
    "screenshot",
    "general",
]


def is_guarded(intent: str) -> bool:
    """
    Returns True if the intent requires authorization.
    Returns False if it's safe to run without confirmation.

    Parameters:
      intent — the intent label from detector.py
    """
    guarded = intent in GUARDED_INTENTS

    if ENABLE_LOGS:
        status = "GUARDED" if guarded else "SAFE"
        print(f"[LoginGuard] Intent '{intent}' is {status}.")

    return guarded


def is_safe(intent: str) -> bool:
    """
    Returns True if the intent is safe to run immediately.
    """
    return intent in SAFE_INTENTS


def guard_check(intent: str, user_input: str, auth, speaker, listener) -> bool:
    """
    Full guard check for an intent.
    If the intent is guarded, requests authorization.
    If safe, passes through immediately.

    Parameters:
      intent     — detected intent label
      user_input — original user command
      auth       — the auth module
      speaker    — the speaker module
      listener   — the listener module

    Returns True if execution is allowed, False if blocked.
    """
    if is_safe(intent):
        if ENABLE_LOGS:
            print(f"[LoginGuard] '{intent}' passed without auth.")
        return True

    if is_guarded(intent):
        if ENABLE_LOGS:
            print(f"[LoginGuard] '{intent}' requires authorization.")
        return auth.request(user_input, speaker, listener)

    # Unknown intent — block by default for safety
    if ENABLE_LOGS:
        print(f"[LoginGuard] Unknown intent '{intent}'. Blocking by default.")
    speaker.say("Sir, I am not sure how to handle that safely. Please try again.")
    return False