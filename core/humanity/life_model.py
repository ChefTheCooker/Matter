# ============================================================
#  MATTER — core/humanity/life_model.py
#  Matter's understanding of your life.
#  Reads raw activity logs and finds patterns:
#    - What time do you usually start working?
#    - Which apps do you always use together?
#    - How long since you took a break?
#    - Have you been isolated lately?
#
#  LifeModel doesn't act on anything. It just builds a picture.
#  HumanityEngine reads that picture and decides what to do.
# ============================================================

import os
import json
from datetime import datetime, date, timedelta
from collections import defaultdict, Counter

from core.config import ENABLE_LOGS
from core.humanity.activity_watcher import get_recent_logs, get_today_log

# ── Where the life model snapshot is saved ────────────────
#  This is a summary file — not the raw logs.
#  It's what HumanityEngine reads to make decisions quickly.
MODEL_FILE = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "life_model.json"
)


# ── App categories ────────────────────────────────────────
#  Groups apps into what kind of activity they represent.
#  This is how Matter understands "you've been coding for 3 hours"
#  rather than just "you've been in 'code' for 3 hours."

APP_CATEGORIES = {
    "work":        ["code", "word", "excel", "powerpoint", "notion", "obsidian", "notepad"],
    "coding":      ["code", "pycharm", "intellij", "vim", "neovim", "terminal", "cmd", "powershell"],
    "browser":     ["chrome", "firefox", "edge", "brave", "opera"],
    "social":      ["discord", "telegram", "whatsapp", "slack", "teams", "zoom"],
    "media":       ["spotify", "vlc", "netflix", "youtube", "mpv"],
    "gaming":      ["steam", "epicgameslauncher", "roblox", "minecraft"],
    "creative":    ["photoshop", "illustrator", "premiere", "davinci", "figma", "blender"],
    "streaming":   ["obs", "streamlabs"],
    "system":      ["explorer", "taskmgr", "settings", "controlpanel"],
}


def _categorise_app(app_name: str) -> str:
    """
    Returns the category for an app name.
    Falls back to 'other' if not recognised.

    Why this matters: Matter shouldn't think you're "working"
    when you're on Discord. Categories let it reason about
    what you're actually doing with your time.
    """
    app = app_name.lower()
    for category, apps in APP_CATEGORIES.items():
        if any(a in app for a in apps):
            return category
    return "other"


# ── Pattern analysis ──────────────────────────────────────

def analyse_recent(days: int = 7) -> dict:
    """
    Analyses the last N days of activity logs and returns
    a structured model of the user's patterns.

    This is the core function of LifeModel.
    Everything else builds on what this returns.
    """
    logs = get_recent_logs(days)

    if not logs:
        return _empty_model()

    # ── Aggregate data across all days ────────────────────
    time_by_category = defaultdict(int)     # category → total seconds
    time_by_app      = defaultdict(int)     # app → total seconds
    start_hours      = []                   # what hour did each day start?
    end_hours        = []                   # what hour did each day end?
    daily_totals     = {}                   # date → total active seconds
    app_sequences    = []                   # ordered list of apps used

    for day, sessions in logs.items():
        if not sessions:
            continue

        day_total = 0
        day_apps  = []

        for session in sessions:
            app      = session.get("app", "unknown")
            duration = session.get("duration", 0)
            started  = session.get("started", "")

            # Accumulate time
            time_by_app[app]                          += duration
            time_by_category[_categorise_app(app)]    += duration
            day_total                                  += duration
            day_apps.append(app)

            # Extract start/end hours
            if started:
                try:
                    hour = datetime.fromisoformat(started).hour
                    start_hours.append(hour)
                except Exception:
                    pass

        daily_totals[day] = day_total
        app_sequences.extend(day_apps)

    # ── Derive insights from aggregated data ──────────────

    # Typical work start hour — median of all first-app hours
    typical_start = _median(start_hours) if start_hours else None

    # Most used app overall
    top_app = max(time_by_app, key=lambda k: time_by_app.get(k) or 0) if time_by_app else None

    # Most used category
    top_category = max(time_by_category, key=lambda k: time_by_category.get(k) or 0) if time_by_category else None

    # Average daily active time in minutes
    avg_daily_minutes = (
        int(sum(daily_totals.values()) / len(daily_totals) / 60)
        if daily_totals else 0
    )

    # Detect isolation: days with zero social app usage
    isolation_days = _count_isolation_days(logs)

    # Common app pairs — apps often used in the same session
    common_pairs = _find_app_pairs(logs)

    model = {
        "analysed_days":      days,
        "generated_at":       datetime.now().isoformat(timespec="seconds"),
        "typical_start_hour": typical_start,
        "top_app":            top_app,
        "top_category":       top_category,
        "avg_daily_minutes":  avg_daily_minutes,
        "isolation_days":     isolation_days,
        "time_by_category":   dict(time_by_category),
        "time_by_app":        dict(sorted(time_by_app.items(), key=lambda x: -x[1])[:10]),
        "common_app_pairs":   common_pairs,
        "daily_totals":       daily_totals,
    }

    _save_model(model)

    if ENABLE_LOGS:
        print(f"[LifeModel] Model updated. Top category: {top_category} | Isolation days: {isolation_days}")

    return model


def get_today_summary() -> dict:
    """
    Returns a quick summary of what the user has done today so far.
    Used by HumanityEngine to make real-time decisions.
    """
    sessions = get_today_log()

    if not sessions:
        return {"active_minutes": 0, "categories": {}, "apps": []}

    time_by_category = defaultdict(int)
    apps_used = []

    for session in sessions:
        app      = session.get("app", "unknown")
        duration = session.get("duration", 0)
        time_by_category[_categorise_app(app)] += duration
        apps_used.append(app)

    return {
        "active_minutes":  int(sum(s.get("duration", 0) for s in sessions) / 60),
        "categories":      dict(time_by_category),
        "apps":            list(dict.fromkeys(apps_used)),  # unique, order preserved
        "session_count":   len(sessions),
    }


# ── Specific insight queries ──────────────────────────────
#  These are called by HumanityEngine when it wants to know
#  something specific about the user's state right now.

def has_been_isolated(threshold_days: int = 3) -> bool:
    """
    Returns True if the user has had no social app activity
    for the last N days. Used to trigger the loneliness check.
    """
    logs = get_recent_logs(threshold_days)
    for day, sessions in logs.items():
        for session in sessions:
            if _categorise_app(session.get("app", "")) == "social":
                return False
    return True


def minutes_since_break() -> int:
    """
    Returns how many minutes the user has been continuously active today.
    A 'break' is defined as a gap of 15+ minutes with no app activity.
    """
    sessions = get_today_log()
    if not sessions:
        return 0

    # Find the last gap > 15 minutes
    last_break_end = None

    for i in range(1, len(sessions)):
        prev_end   = sessions[i - 1].get("ended", "")
        curr_start = sessions[i].get("started", "")

        if not prev_end or not curr_start:
            continue

        try:
            gap = (
                datetime.fromisoformat(curr_start) -
                datetime.fromisoformat(prev_end)
            ).total_seconds() / 60

            if gap >= 15:
                last_break_end = datetime.fromisoformat(curr_start)
        except Exception:
            continue

    if last_break_end:
        return int((datetime.now() - last_break_end).total_seconds() / 60)

    # No break found — count from first session of the day
    try:
        first_start = datetime.fromisoformat(sessions[0]["started"])
        return int((datetime.now() - first_start).total_seconds() / 60)
    except Exception:
        return 0


def is_in_coding_session() -> bool:
    """Returns True if the user has been coding in the last 30 minutes."""
    sessions = get_today_log()
    cutoff = datetime.now() - timedelta(minutes=30)

    for session in reversed(sessions):
        try:
            ended = datetime.fromisoformat(session.get("ended", ""))
            if ended >= cutoff and _categorise_app(session.get("app", "")) == "coding":
                return True
        except Exception:
            continue

    return False


def predict_next_app(current_app: str) -> str | None:
    """
    Given the current app, predicts what the user will open next
    based on their historical patterns.

    How: Looks at all sessions where current_app appeared,
    and finds the most common app that came right after it.
    """
    logs = get_recent_logs(14)  # 2 weeks of history
    transitions = defaultdict(Counter)

    for day, sessions in logs.items():
        for i in range(len(sessions) - 1):
            this_app = sessions[i].get("app", "")
            next_app = sessions[i + 1].get("app", "")
            if this_app and next_app:
                transitions[this_app][next_app] += 1

    next_counts = transitions.get(current_app)
    if not next_counts:
        return None

    return next_counts.most_common(1)[0][0]


# ── Helpers ───────────────────────────────────────────────

def _median(values: list) -> float:
    if not values:
        return 0
    sorted_vals = sorted(values)
    mid = len(sorted_vals) // 2
    return sorted_vals[mid]


def _count_isolation_days(logs: dict) -> int:
    """Counts days where no social app was used."""
    isolated = 0
    for day, sessions in logs.items():
        has_social = any(
            _categorise_app(s.get("app", "")) == "social"
            for s in sessions
        )
        if not has_social:
            isolated += 1
    return isolated


def _find_app_pairs(logs: dict) -> list:
    """
    Finds pairs of apps commonly used in the same day.
    Returns the top 5 pairs as a list of [app1, app2] lists.
    """
    pair_counts = Counter()

    for day, sessions in logs.items():
        apps = list(dict.fromkeys(s.get("app", "") for s in sessions))
        for i in range(len(apps)):
            for j in range(i + 1, len(apps)):
                pair = tuple(sorted([apps[i], apps[j]]))
                pair_counts[pair] += 1

    return [list(pair) for pair, _ in pair_counts.most_common(5)]


def _empty_model() -> dict:
    return {
        "analysed_days":      0,
        "generated_at":       datetime.now().isoformat(timespec="seconds"),
        "typical_start_hour": None,
        "top_app":            None,
        "top_category":       None,
        "avg_daily_minutes":  0,
        "isolation_days":     0,
        "time_by_category":   {},
        "time_by_app":        {},
        "common_app_pairs":   [],
        "daily_totals":       {},
    }


def _save_model(model: dict):
    os.makedirs(os.path.dirname(MODEL_FILE), exist_ok=True)
    with open(MODEL_FILE, "w") as f:
        json.dump(model, f, indent=2)


def load_model() -> dict:
    """Loads the last saved model snapshot from disk."""
    if not os.path.exists(MODEL_FILE):
        return _empty_model()
    try:
        with open(MODEL_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return _empty_model()