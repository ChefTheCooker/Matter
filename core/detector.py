# ============================================================
#  MATTER — core/detector.py
#  Matter's intent detector. Figures out what the user wants
#  before passing it to the right handler in engine.py.
#  No API call needed — fast keyword-based classification.
# ============================================================

from core.config import ENABLE_LOGS


# ── Intent definitions ────────────────────────────────────
#  Each intent has a set of trigger keywords.
#  Order matters — more specific intents should come first.

INTENTS = {

    # ── Mode triggers ──────────────────────────────────────
    "stream_mode": [
        "prepare for stream", "setup stream", "start stream",
        "streaming mode", "get ready to stream", "launch stream"
    ],
    "coding_mode": [
        "prepare for coding", "setup coding", "coding mode",
        "start coding", "get ready to code", "launch coding"
    ],

    # ── App control ────────────────────────────────────────
    "open_app": [
        "open", "launch", "start", "run", "pull up"
    ],
    "close_app": [
        "close", "shut down", "kill", "exit", "quit"
    ],

    # ── Web & search ───────────────────────────────────────
    "search_web": [
        "search for", "look up", "google", "find me",
        "search the web", "browse", "search online"
    ],
    "open_url": [
        "open website", "go to", "visit", "navigate to",
        "open link", "open url"
    ],

    # ── System control ─────────────────────────────────────
    "volume_up": [
        "volume up", "turn up", "increase volume", "louder"
    ],
    "volume_down": [
        "volume down", "turn down", "decrease volume", "quieter"
    ],
    "mute": [
        "mute", "silence", "shut up", "quiet"
    ],
    "screenshot": [
        "take a screenshot", "screenshot", "capture screen", "snap screen"
    ],
    "shutdown": [
        "shut down the computer", "power off", "turn off the pc",
        "shutdown pc", "turn off computer"
    ],
    "restart": [
        "restart", "reboot", "restart the computer", "reboot pc"
    ],
    "sleep": [
        "sleep", "put to sleep", "hibernate", "sleep mode"
    ],

    # ── File & folder ──────────────────────────────────────
    "open_file": [
        "open file", "open folder", "open document", "open my"
    ],
    "create_file": [
        "create file", "make a file", "new file", "create document",
        "write a file"
    ],

    # ── News & world updates ───────────────────────────────
    "get_news": [
        "what's happening", "latest news", "news today",
        "what's in the news", "current events", "world news",
        "tell me the news", "any updates"
    ],

    # ── Weather ────────────────────────────────────────────
    "get_weather": [
        "weather", "temperature outside", "what's the weather",
        "will it rain", "forecast", "how hot", "how cold"
    ],

    # ── Time & date ────────────────────────────────────────
    "get_time": [
        "what time", "current time", "what's the time"
    ],
    "get_date": [
        "what's the date", "today's date", "what day is it",
        "what month", "current date"
    ],

    # ── Reminders & alarms ─────────────────────────────────
    "set_reminder": [
        "remind me", "set a reminder", "don't let me forget",
        "alert me", "notify me"
    ],
    "set_alarm": [
        "set an alarm", "wake me up", "alarm for", "set alarm"
    ],
    "set_timer": [
        "set a timer", "timer for", "count down", "countdown"
    ],

    # ── Wikipedia & knowledge ──────────────────────────────
    "wikipedia": [
        "who is", "what is", "tell me about", "explain",
        "define", "wikipedia", "look up", "what do you know about"
    ],

    # ── Memory & session ──────────────────────────────────
    "clear_memory": [
        "forget everything", "clear memory", "fresh start",
        "reset conversation", "start over", "wipe memory"
    ],

    # ── Identity ───────────────────────────────────────────
    "who_are_you": [
        "who are you", "what are you", "introduce yourself",
        "what can you do", "your name", "tell me about yourself"
    ],

    # ── Gratitude / smalltalk ─────────────────────────────
    "thanks": [
        "thank you", "thanks", "good job", "well done",
        "nice work", "appreciate it"
    ],

    # ── Exit / shutdown Matter ─────────────────────────────
    "exit_matter": [
        "goodbye", "bye", "shut yourself down", "go offline",
        "turn yourself off", "exit matter", "stop matter",
        "close matter", "that's all"
    ],
}


# ── Detector ──────────────────────────────────────────────

def detect(user_input: str) -> str:
    """
    Takes raw user input and returns the most likely intent label.
    Falls back to 'general' if nothing matches — which means
    the brain (Claude) will handle it conversationally.

    Parameters:
      user_input — transcribed text from the listener

    Returns:
      A string intent label e.g. 'open_app', 'get_news', 'general'
    """
    text = user_input.lower().strip()

    for intent, keywords in INTENTS.items():
        for keyword in keywords:
            if keyword in text:
                if ENABLE_LOGS:
                    print(f"[Detector] Intent matched: '{intent}' via '{keyword}'")
                return intent

    # No match — let Claude handle it
    if ENABLE_LOGS:
        print(f"[Detector] No intent matched. Routing to general brain.")

    return "general"


def extract_app_name(user_input: str) -> str:
    """
    Extracts the app name from phrases like 'open spotify' or 'close chrome'.
    Used by engine.py when handling open_app / close_app intents.

    Returns the app name as a lowercase string, or empty string if not found.
    """
    text = user_input.lower().strip()

    trigger_words = [
        "open", "launch", "start", "run", "pull up",
        "close", "shut down", "kill", "exit", "quit"
    ]

    for trigger in trigger_words:
        if text.startswith(trigger):
            app = text.replace(trigger, "").strip()
            if ENABLE_LOGS:
                print(f"[Detector] App name extracted: '{app}'")
            return app

    return ""


def extract_search_query(user_input: str) -> str:
    """
    Extracts the search query from phrases like 'search for best laptops'.
    Used by engine.py when handling search_web intent.

    Returns the search query as a string.
    """
    text = user_input.lower().strip()

    prefixes = [
        "search for", "look up", "google", "find me",
        "search the web for", "search online for", "browse for"
    ]

    for prefix in prefixes:
        if text.startswith(prefix):
            query = text.replace(prefix, "").strip()
            if ENABLE_LOGS:
                print(f"[Detector] Search query extracted: '{query}'")
            return query

    return user_input  # Fall back to full input as query


def extract_reminder_text(user_input: str) -> str:
    """
    Extracts reminder content from phrases like 'remind me to call mom at 5'.
    Used by engine.py when handling set_reminder intent.
    """
    text = user_input.lower().strip()

    prefixes = ["remind me to", "remind me", "don't let me forget to",
                "don't let me forget", "alert me to", "notify me to"]

    for prefix in prefixes:
        if prefix in text:
            reminder = text.split(prefix, 1)[-1].strip()
            if ENABLE_LOGS:
                print(f"[Detector] Reminder extracted: '{reminder}'")
            return reminder

    return user_input