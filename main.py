# ============================================================
#  MATTER — main.py
#  Entry point. Boots everything and ties it together.
# ============================================================
from core import notifications

import threading
import time
import sys

from core    import config
from core    import listener
from core    import speaker
from core    import detector
from core    import engine
from core    import smart_home
from brain   import claude
from auth    import auth
from auth    import login_guard
from ui.ui   import MatterUI
from typing  import Optional   

# ── Global UI instance ────────────────────────────────────
#  Starts as None. Created in start_matter() after boot screen closes.
ui: Optional[MatterUI] = None


def safe_ui(method: str, *args):
    """
    Calls a method on the UI safely from any thread.
    Uses the method name as a string so Pylance doesn't
    panic about ui being None  when the call is constructed.
    If ui isn't ready yet, the call is silently dropped.
    """
    if ui is not None:
        getattr(ui, method)(*args)


# ── Command router ────────────────────────────────────────

def handle_command(user_input: str):
    if not user_input.strip():
        return

    safe_ui("log_user", user_input)
    safe_ui("set_thinking")

    intent  = detector.detect(user_input)
    allowed = login_guard.guard_check(
        intent, user_input, auth, speaker, listener
    )

    if not allowed:
        safe_ui("set_idle")
        return

    response = ""

    if intent == "stream_mode":
        launched = engine.prepare_stream()
        response = f"Sir, stream setup is ready. I've opened: {', '.join(launched)}."

    elif intent == "coding_mode":
        launched = engine.prepare_coding()
        response = f"Sir, coding setup is ready. I've opened: {', '.join(launched)}."

    elif intent == "open_app":
        app     = detector.extract_app_name(user_input)
        success = engine.open_app(app)
        response = f"Opening {app}, Sir." if success else f"Sir, I couldn't open {app}."

    elif intent == "close_app":
        app     = detector.extract_app_name(user_input)
        success = engine.close_app(app)
        response = f"Closed {app}, Sir." if success else f"Sir, I couldn't close {app}."

    elif intent == "search_web":
        query = detector.extract_search_query(user_input)
        engine.search_web(query)
        response = f"Searching for {query}, Sir."

    elif intent == "open_url":
        words = user_input.lower().split()
        url   = words[-1] if words else ""
        engine.open_url(url)
        response = f"Opening {url}, Sir."

    elif intent == "wikipedia":
        query    = detector.extract_search_query(user_input)
        response = engine.search_wikipedia(query)

    elif intent == "get_news":
        headlines = engine.get_headlines()
        response  = "Sir, here are the latest headlines. " + ". ".join(headlines)

    elif intent == "get_time":
        response = engine.get_time()

    elif intent == "get_date":
        response = engine.get_date()

    elif intent == "volume_up":
        engine.set_volume(80)
        response = "Volume raised, Sir."

    elif intent == "volume_down":
        engine.set_volume(30)
        response = "Volume lowered, Sir."

    elif intent == "mute":
        engine.set_volume(0)
        response = "Muted, Sir."

    elif intent == "screenshot":
        success  = engine.take_screenshot()
        response = "Screenshot taken, Sir." if success else "Sir, I couldn't take the screenshot."

    elif intent == "shutdown":
        engine.shutdown_pc()
        response = "Shutting down, Sir. Goodbye."

    elif intent == "restart":
        engine.restart_pc()
        response = "Restarting, Sir."

    elif intent == "sleep":
        engine.sleep_pc()
        response = "Going to sleep, Sir."
    elif intent == "set_reminder":
        parsed = notifications.parse_reminder_from_voice(user_input)
        if parsed is not None:
            notifications.add_reminder(**parsed)
            strict_note = " This is a strict reminder — I will verify completion." if parsed["strict"] else ""
            response = f"Got it, Sir. I'll remind you to {parsed['text']} at {parsed['remind_at']}.{strict_note}"
        else:
            response = "Sir, I couldn't parse that reminder. Try saying the time more clearly."

    elif intent == "who_are_you":
        response = (
            f"I am {config.ASSISTANT_NAME}, your personal AI assistant. "
            f"I can control your PC, browse the web, manage your smart home, "
            f"fetch news, answer questions, and much more — all by your command, Sir."
        )

    elif intent == "thanks":
        response = "Always, Sir."

    elif intent == "smart_home_control":
        action = "on" if "on" in user_input else "off" if "off" in user_input else "toggle"
        device = user_input.lower()
        for word in ["turn", "switch", "on", "off", "the", "my", action]:
            device = device.replace(word, "").strip()
        response = smart_home.control(device, action)

    elif intent == "exit_matter":
        response = "Goodbye, Sir. Matter going offline."
        speaker.say(response)
        safe_ui("log_matter", response)
        time.sleep(2)
        safe_ui("quit")
        sys.exit(0)

    else:
        response = claude.think(user_input)

    safe_ui("set_speaking")
    speaker.say(response)
    safe_ui("log_matter", response)
    safe_ui("set_idle")


# ── Wake word callback ────────────────────────────────────

def on_wake():
    safe_ui("set_listening")
    safe_ui("log_system", "Wake word detected")
    speaker.say("Yes, Sir?", blocking=False)


# ── Boot logic ────────────────────────────────────────────

def boot():
    if config.ENABLE_LOGS:
        print(f"[Main] Booting {config.ASSISTANT_NAME}...")

    listener.preload_whisper()

    safe_ui("log_system", "Scanning for smart devices...")
    notifications.start(speaker, ui)
    smart_home.scan_all()

    def _wait_for_scan():
        while not smart_home._scan_complete:
            time.sleep(0.5)
        count = smart_home.device_count()
        safe_ui("update_device_count", count)
        safe_ui("log_system", f"{count} smart device(s) found")

    threading.Thread(target=_wait_for_scan, daemon=True).start()

    listener.set_wake_callback(on_wake)
    listener.set_input_callback(handle_command)
    listener.start()

    safe_ui("log_system", "Listening for wake word...")

    if ui is not None:
        ui.set_text_callback(handle_command)

    time.sleep(1)
    greeting = f"Matter online. Good to see you, Sir. Say '{config.WAKE_WORD}' to begin."
    speaker.say(greeting)
    safe_ui("log_matter", greeting)
    safe_ui("set_idle")

    if config.ENABLE_LOGS:
        print(f"[Main] {config.ASSISTANT_NAME} is online.")


# ── Entry point ───────────────────────────────────────────

def start_matter():
    """
    Called after boot sequence window closes.
    Creates the UI then boots everything in a background thread.
    """
    global ui
    ui = MatterUI()
    threading.Thread(target=boot, daemon=True).start()
    ui.run()


if __name__ == "__main__":
    from ui.boot import play
    play(on_complete=start_matter)