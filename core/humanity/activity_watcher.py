# ============================================================
#  MATTER — core/humanity/activity_watcher.py
#  Matter's eyes. Watches what the user does on the PC —
#  which apps they open, when, and for how long.
#  Runs silently in the background. Never intrudes.
#
#  What it tracks:
#    - Active window / app name + timestamps
#    - Session start and end times
#    - Daily usage patterns over time
#
#  What it deliberately does NOT track:
#    - Keystrokes (never)
#    - Screenshots (never without permission)
#    - File contents (only filenames, only if you add that later)
#
#  This data feeds into LifeModel, which finds patterns.
#  ActivityWatcher just records — it doesn't interpret.
# ============================================================

import time
import json
import os
import threading
from datetime import datetime, date

from core.config import ENABLE_LOGS

# ── Where activity logs live ──────────────────────────────
#  One JSON file per day. Keeps things simple and inspectable.
#  You can open data/activity/2025-01-30.json and read it yourself.
ACTIVITY_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "activity")

# ── How often to check the active window (seconds) ───────
#  Every 5 seconds is frequent enough to be useful,
#  not so frequent it hammers the CPU.
POLL_INTERVAL = 5

# ── Minimum time in an app before it counts (seconds) ────
#  Filters out accidental flickers — if you're in an app
#  for less than 10 seconds, it doesn't get logged.
MIN_SESSION_DURATION = 10


# ── Platform-specific window detection ───────────────────
#  We use different methods depending on the OS.
#  Matter runs on Windows, so we use win32gui.
#  The try/except means it won't crash on other platforms.

try:
    import win32gui
    import win32process
    import psutil   #type :ignore 
    WINDOWS_AVAILABLE = True
except ImportError:
    WINDOWS_AVAILABLE = False
    if ENABLE_LOGS:
        print("[ActivityWatcher] win32gui or psutil not installed. Install with:")
        print("  pip install pywin32 psutil")


# ── Internal state ────────────────────────────────────────
_watching = False           # Is the watcher running?
_current_app = None         # What app is active right now?
_current_start = None       # When did the user switch to it?
_watcher_thread = None      # The background thread


# ── Core window detection ─────────────────────────────────

def _get_active_app() -> str | None:
    """
    Returns the name of the currently active application.
    Returns None if it can't be determined.

    How it works on Windows:
      1. win32gui.GetForegroundWindow() → gets the active window handle
      2. win32process.GetWindowThreadProcessId() → gets the process ID
      3. psutil.Process(pid).name() → gets the app name from that PID

    Why this chain? Because Windows gives you a window handle first,
    not an app name. You have to trace it back through the process table.
    """
    if not WINDOWS_AVAILABLE:
        return None

    try:
        hwnd = win32gui.GetForegroundWindow()  # type: ignore[possibly-undefined]
        if not hwnd:
            return None

        _, pid = win32process.GetWindowThreadProcessId(hwnd)  # type: ignore[possibly-undefined]
        process = psutil.Process(pid)  # type: ignore[possibly-undefined]
        return process.name().replace(".exe", "").lower()

    except Exception:
        return None


# ── Logging ───────────────────────────────────────────────

def _ensure_activity_dir():
    """Creates the data/activity/ folder if it doesn't exist."""
    os.makedirs(ACTIVITY_DIR, exist_ok=True)


def _get_log_path() -> str:
    """Returns the path to today's activity log file."""
    today = str(date.today())
    return os.path.join(ACTIVITY_DIR, f"{today}.json")


def _load_today() -> list:
    """
    Loads today's activity log from disk.
    Returns an empty list if today has no log yet.
    """
    path = _get_log_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return []


def _save_entry(app: str, started: str, ended: str, duration_seconds: int):
    """
    Saves a single app session to today's log.

    Each entry looks like this in the JSON:
    {
      "app": "chrome",
      "started": "2025-01-30T09:14:22",
      "ended":   "2025-01-30T09:31:05",
      "duration": 1003
    }

    Why append rather than rewrite? Because if Matter crashes,
    you don't lose the whole day's log — only the last entry.
    """
    _ensure_activity_dir()
    log = _load_today()

    log.append({
        "app":      app,
        "started":  started,
        "ended":    ended,
        "duration": duration_seconds,   # in seconds
        "date":     str(date.today()),
    })

    path = _get_log_path()
    with open(path, "w") as f:
        json.dump(log, f, indent=2)

    if ENABLE_LOGS:
        print(f"[ActivityWatcher] Logged: {app} for {duration_seconds}s")


# ── The watcher loop ──────────────────────────────────────

def _watch_loop():
    """
    The main background loop. Runs every POLL_INTERVAL seconds.
    Detects when the user switches apps and logs the previous session.

    The logic:
      - Check what app is active right now
      - If it's the same as before → keep waiting
      - If it changed → the previous session just ended, log it
      - Start tracking the new app
    """
    global _watching, _current_app, _current_start

    if ENABLE_LOGS:
        print("[ActivityWatcher] Watcher loop started.")

    while _watching:
        active = _get_active_app()

        if active and active != _current_app:
            # The app changed. Log the previous session if it was long enough.
            if _current_app and _current_start:
                now = datetime.now()
                duration = int((now - _current_start).total_seconds())

                if duration >= MIN_SESSION_DURATION:
                    _save_entry(
                        app=_current_app,
                        started=_current_start.isoformat(timespec="seconds"),
                        ended=now.isoformat(timespec="seconds"),
                        duration_seconds=duration,
                    )

            # Start tracking the new app
            _current_app   = active
            _current_start = datetime.now()

        time.sleep(POLL_INTERVAL)

    # Watcher stopped — log whatever was active at shutdown
    if _current_app and _current_start:
        now = datetime.now()
        duration = int((now - _current_start).total_seconds())
        if duration >= MIN_SESSION_DURATION:
            _save_entry(
                app=_current_app,
                started=_current_start.isoformat(timespec="seconds"),
                ended=now.isoformat(timespec="seconds"),
                duration_seconds=duration,
            )

    if ENABLE_LOGS:
        print("[ActivityWatcher] Watcher loop stopped.")


# ── Public API ────────────────────────────────────────────

def start():
    """
    Starts the activity watcher in a background thread.
    Non-blocking — Matter runs normally while this watches.
    Safe to call multiple times — won't start twice.
    """
    global _watching, _watcher_thread

    if _watching:
        if ENABLE_LOGS:
            print("[ActivityWatcher] Already running.")
        return

    _watching = True
    _watcher_thread = threading.Thread(target=_watch_loop, daemon=True)
    _watcher_thread.start()

    if ENABLE_LOGS:
        print("[ActivityWatcher] Started.")


def stop():
    """Stops the watcher. The loop will finish its current cycle then exit."""
    global _watching
    _watching = False

    if ENABLE_LOGS:
        print("[ActivityWatcher] Stopping...")


def get_today_log() -> list:
    """
    Returns today's full activity log as a list of session dicts.
    Used by LifeModel to find patterns.
    """
    return _load_today()


def get_log_for_date(target_date: str) -> list:
    """
    Returns the activity log for a specific date.
    target_date format: 'YYYY-MM-DD'
    """
    path = os.path.join(ACTIVITY_DIR, f"{target_date}.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return []


def get_recent_logs(days: int = 7) -> dict:
    """
    Returns activity logs for the last N days.
    Returns a dict keyed by date string: { "2025-01-30": [...], ... }

    Why a dict? So LifeModel can compare day-by-day easily.
    """
    from datetime import timedelta
    result = {}
    today = date.today()

    for i in range(days):
        target = str(today - timedelta(days=i))
        log = get_log_for_date(target)
        if log:
            result[target] = log

    return result


def is_running() -> bool:
    """Returns True if the watcher is currently active."""
    return _watching