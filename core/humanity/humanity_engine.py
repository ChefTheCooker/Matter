# ============================================================
#  MATTER — core/humanity/humanity_engine.py
#  The decision brain of the Humanity system.
#
#  This is the file where everything comes together.
#  It reads what LifeModel knows about you, decides what
#  Matter should do proactively, and submits those actions
#  to ActionQueue with the right tier.
#
#  It runs on a schedule — every hour while Matter is alive.
#  On the Oracle server, it runs even when you're not at the PC.
#
#  When you return, it reads out everything it queued
#  while you were away. That's the JARVIS moment.
# ============================================================

import time
import threading
import schedule                          # type: ignore # pip install schedule
from datetime import datetime, date

from core.config import ENABLE_LOGS
from core.humanity import activity_watcher
from core.humanity import life_model
from core.humanity import action_queue
from core.humanity.action_queue import Tier

# ── How often the engine thinks (minutes) ────────────────
#  Every 60 minutes is the right balance — frequent enough
#  to feel aware, not so frequent it hammers the CPU or
#  makes decisions on too little data.
THINK_INTERVAL_MINUTES = 60

# ── Break reminder threshold (minutes) ───────────────────
#  If you've been active for longer than this without a break,
#  Matter will gently suggest one.
BREAK_THRESHOLD_MINUTES = 90

# ── Isolation threshold (days) ────────────────────────────
#  If Matter sees no social app usage for this many days,
#  it flags it. Not to lecture — just to notice.
ISOLATION_THRESHOLD_DAYS = 3

# ── Internal state ────────────────────────────────────────
_engine_running = False
_scheduler_thread = None
_away_since = None          # Timestamp of when the user was last seen


# ============================================================
#  THE DECISION LOOP
#  This is the core of Humanity. Called every hour.
#  Each check is independent — if one fails, the others run.
# ============================================================

def think():
    """
    The main decision function. Runs every THINK_INTERVAL_MINUTES.
    Checks several conditions and submits appropriate actions.

    Structure: a series of independent checks.
    Each check asks one question about the user's state
    and decides whether to act, and at what tier.

    Why independent checks rather than one big function?
    Because if the break check fails due to a bug, the
    isolation check should still run. Resilience matters
    in a system that runs unattended.
    """
    if ENABLE_LOGS:
        print(f"[HumanityEngine] Thinking... ({datetime.now().strftime('%H:%M')})")

    try:
        _check_break_needed()
    except Exception as e:
        if ENABLE_LOGS:
            print(f"[HumanityEngine] Break check failed: {e}")

    try:
        _check_isolation()
    except Exception as e:
        if ENABLE_LOGS:
            print(f"[HumanityEngine] Isolation check failed: {e}")

    try:
        _check_workspace_prep()
    except Exception as e:
        if ENABLE_LOGS:
            print(f"[HumanityEngine] Workspace prep check failed: {e}")

    try:
        _check_long_session()
    except Exception as e:
        if ENABLE_LOGS:
            print(f"[HumanityEngine] Long session check failed: {e}")

    if ENABLE_LOGS:
        print(f"[HumanityEngine] Think cycle complete. "
              f"Pending actions: {action_queue.count_pending()}")


# ============================================================
#  INDIVIDUAL CHECKS
#  Each function answers one specific question about the
#  user's state and decides what — if anything — to do.
# ============================================================

def _check_break_needed():
    """
    Checks if the user has been active too long without a break.

    How it works:
      life_model.minutes_since_break() counts continuous active
      minutes since the last 15-minute gap in app usage.
      If that number exceeds BREAK_THRESHOLD_MINUTES, Matter
      queues a gentle suggestion.

    Tier: FREE — this is a suggestion shown in the UI,
    not an action taken on the user's behalf.
    Matter doesn't pause your work or interrupt you —
    it just queues a note for next time you interact.
    """
    minutes = life_model.minutes_since_break()

    if minutes >= BREAK_THRESHOLD_MINUTES:
        action_queue.submit(
            action_type="queue_suggestion",
            description=(
                f"Sir, you have been active for {minutes} minutes without a break. "
                f"A short rest would do you good."
            ),
            payload={"type": "break_reminder", "minutes_active": minutes}
        )

        if ENABLE_LOGS:
            print(f"[HumanityEngine] Break reminder queued. Active: {minutes}m")


def _check_isolation():
    """
    Checks if the user has had no social contact for several days.

    'Social contact' is defined as opening a social app —
    Discord, WhatsApp, Telegram, etc. It's an imperfect signal,
    but it's what we have without being invasive.

    This is one of the most important checks in the whole system.
    The goal of Matter is to push the user toward real human
    connection, not to replace it. If you haven't talked to
    anyone in three days, Matter notices and says something.
    But it says it with warmth, not alarm.

    Tier: FREE — queued as a gentle check-in message.
    Matter never contacts anyone on your behalf (that's CHECK tier).
    It just surfaces the observation to you.
    """
    if life_model.has_been_isolated(ISOLATION_THRESHOLD_DAYS):
        # Don't spam this — only queue if there's no pending isolation check already
        pending = action_queue.get_pending()
        already_queued = any(
            p.get("payload", {}).get("type") == "isolation_check"
            for p in pending
        )

        if not already_queued:
            action_queue.submit(
                action_type="queue_suggestion",
                description=(
                    f"Sir, it has been {ISOLATION_THRESHOLD_DAYS}+ days since I have seen "
                    f"you open Discord, WhatsApp, or any social app. "
                    f"Is everything alright? Consider reaching out to someone today."
                ),
                payload={"type": "isolation_check", "days": ISOLATION_THRESHOLD_DAYS}
            )

            if ENABLE_LOGS:
                print(f"[HumanityEngine] Isolation check queued.")


def _check_workspace_prep():
    """
    Checks if Matter should prepare a workspace before the user
    needs it — based on their historical patterns.

    How it works:
      LifeModel tracks which apps the user opens together most often.
      If it's currently the time of day when the user usually starts
      a coding session, and the coding apps aren't open yet,
      Matter queues an offer to open them.

    Why CHECK tier and not FREE?
      Opening apps is noticeable. If Matter silently opened OBS,
      Discord, and Spotify without asking, it would feel invasive.
      So it queues a question: "Sir, it's around the time you
      usually start coding. Want me to set up your workspace?"

    Tier: CHECK — asks before opening anything.
    """
    model = life_model.load_model()
    typical_start = model.get("typical_start_hour")

    if typical_start is None:
        return  # Not enough data yet to predict

    current_hour = datetime.now().hour
    top_category = model.get("top_category", "")

    # Is it within 30 minutes of their typical start time?
    within_window = abs(current_hour - typical_start) <= 0

    if within_window and top_category in ("coding", "work"):
        # Don't spam — check if already queued today
        pending = action_queue.get_pending()
        already_queued = any(
            p.get("payload", {}).get("type") == "workspace_prep"
            and p.get("payload", {}).get("date") == str(date.today())
            for p in pending
        )

        if not already_queued:
            action_queue.submit(
                action_type="prep_workspace",
                description=(
                    f"Sir, it is around the time you usually start your {top_category} session. "
                    f"Shall I set up your workspace?"
                ),
                payload={
                    "type":     "workspace_prep",
                    "date":     str(date.today()),
                    "category": top_category,
                }
            )

            if ENABLE_LOGS:
                print(f"[HumanityEngine] Workspace prep queued for {top_category}.")


def _check_long_session():
    """
    Checks if the user has been in a single app category for
    an unusually long time compared to their own average.

    This is different from the break check.
    The break check is about raw time active.
    This check is about context — if you normally code for
    2 hours but today you've been at it for 5, Matter notices.

    It doesn't judge. It just reflects it back: "Sir, you have
    been coding for 5 hours today. That's more than usual."

    Tier: FREE — observation only, no action taken.
    """
    today = life_model.get_today_summary()
    model = life_model.load_model()

    today_coding = today.get("categories", {}).get("coding", 0) // 60  # minutes
    avg_daily = model.get("avg_daily_minutes", 0)

    # Only flag if today is significantly above their own average
    if today_coding > 0 and avg_daily > 0 and today_coding > (avg_daily * 1.5):
        pending = action_queue.get_pending()
        already_queued = any(
            p.get("payload", {}).get("type") == "long_session"
            and p.get("payload", {}).get("date") == str(date.today())
            for p in pending
        )

        if not already_queued:
            action_queue.submit(
                action_type="queue_suggestion",
                description=(
                    f"Sir, you have been coding for {today_coding} minutes today. "
                    f"Your usual average is around {avg_daily} minutes. "
                    f"You are pushing harder than normal."
                ),
                payload={
                    "type":          "long_session",
                    "date":          str(date.today()),
                    "minutes_today": today_coding,
                    "avg_minutes":   avg_daily,
                }
            )

            if ENABLE_LOGS:
                print(f"[HumanityEngine] Long session flagged: {today_coding}m vs avg {avg_daily}m")


# ============================================================
#  RETURN BRIEFING
#  Called when Matter detects the user has come back to the PC
#  after being away. Reads out everything queued while they
#  were gone. This is the JARVIS moment.
# ============================================================

def get_return_briefing() -> str | None:
    """
    Called at the start of each session by main.py.
    If there are pending queued actions, formats them into
    a spoken briefing for Matter to read aloud.

    Returns a string Matter will speak, or None if nothing queued.

    Example output:
      "Sir, while you were away I noticed three things.
       First, you have been active for 95 minutes without a break.
       Second, it has been four days since you opened a social app.
       Third, it is around the time you usually start coding —
       shall I set up your workspace?"

    Why is this separate from think()?
    Because think() runs every hour — but the briefing only
    happens once, when you sit down. It collects everything
    that accumulated while you were away and delivers it as
    one coherent message, not as separate interruptions.
    """
    pending = action_queue.get_pending()

    if not pending:
        return None

    count = len(pending)

    if count == 1:
        intro = "Sir, while you were away I noticed something."
    else:
        intro = f"Sir, while you were away I noticed {count} things."

    items = []
    for i, action in enumerate(pending[:4]):  # Max 4 items — don't overwhelm
        prefix = ["First", "Second", "Third", "Fourth"][i]
        items.append(f"{prefix}: {action['description']}")

    briefing = intro + " " + " ".join(items)

    # Mark all CHECK-tier items as still pending (user needs to respond)
    # Mark FREE-tier suggestion items as done since we've surfaced them
    for action in pending:
        if action["tier"] == Tier.FREE:
            action_queue.approve(action["id"])

    return briefing


# ============================================================
#  SCHEDULER — runs the engine on a timer
#  Uses the `schedule` library (pip install schedule).
#
#  Why schedule and not threading.Timer?
#  schedule lets you say "every 60 minutes" in plain English
#  and handles edge cases like the system sleeping and waking.
#  threading.Timer fires once and needs to be restarted.
# ============================================================

def _run_scheduler():
    """
    The scheduler loop. Runs in a background thread.
    Calls think() every THINK_INTERVAL_MINUTES minutes.

    This thread runs for the entire lifetime of Matter —
    including when the user is away from the PC.
    On Oracle, this runs 24/7.
    """
    schedule.every(THINK_INTERVAL_MINUTES).minutes.do(think)

    # Also update the life model once per day at 4am —
    # low-traffic time, catches the full previous day's data
    schedule.every().day.at("04:00").do(
        lambda: life_model.analyse_recent(days=7)
    )

    # Clean up old dismissed actions weekly
    schedule.every().sunday.at("03:00").do(
        lambda: action_queue.clear_old_dismissed(days=7)
    )

    if ENABLE_LOGS:
        print(f"[HumanityEngine] Scheduler started. "
              f"Thinking every {THINK_INTERVAL_MINUTES} minutes.")

    while _engine_running:
        schedule.run_pending()
        time.sleep(30)  # Check every 30 seconds — lightweight


# ============================================================
#  PUBLIC API
# ============================================================

def start():
    """
    Starts the full Humanity system:
      1. ActivityWatcher — begins watching the active window
      2. Scheduler — begins the hourly think() cycle
      3. First think() — runs immediately on startup

    Call this from main.py during boot().
    Non-blocking — everything runs in background threads.
    """
    global _engine_running, _scheduler_thread

    if _engine_running:
        if ENABLE_LOGS:
            print("[HumanityEngine] Already running.")
        return

    _engine_running = True

    # Start the activity watcher first — it needs to be
    # collecting data before the engine makes decisions
    activity_watcher.start()

    # Start the scheduler in its own background thread
    _scheduler_thread = threading.Thread(
        target=_run_scheduler,
        daemon=True,        # daemon=True means it dies when main.py exits
        name="HumanityScheduler"
    )
    _scheduler_thread.start()

    # Run one think() immediately so Matter isn't blind
    # for the first hour after startup
    threading.Thread(target=think, daemon=True).start()

    if ENABLE_LOGS:
        print("[HumanityEngine] Humanity system online.")


def stop():
    """
    Stops the engine and the activity watcher.
    Called when Matter shuts down.
    """
    global _engine_running
    _engine_running = False
    activity_watcher.stop()
    schedule.clear()

    if ENABLE_LOGS:
        print("[HumanityEngine] Humanity system offline.")


def is_running() -> bool:
    return _engine_running


def force_think():
    """
    Triggers a think() cycle immediately — outside the schedule.
    Useful for testing. Call this from main.py or the terminal.
    """
    threading.Thread(target=think, daemon=True).start()