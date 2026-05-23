# ============================================================
#  MATTER — core/notifications.py
#  Reminder and notification system with Strict Mode.
#
#  Normal reminder: Matter speaks it, Windows toast fires.
#  Strict reminder: All of the above + webcam photo taken
#                   + Gemini Vision verifies completion.
#                   Only clears when Gemini says yes, or
#                   user explicitly overrides.
#
#  Strict mode tasks: prayer, gym, medication, groceries, study
# ============================================================

import os
import json
import threading
import time
import uuid
import base64
from datetime import datetime, date, timedelta
from typing import Optional

from core.config import ENABLE_LOGS, GEMINI_API_KEY, GEMINI_MODEL

# ── Storage ───────────────────────────────────────────────
REMINDERS_FILE = os.path.join(
    os.path.dirname(__file__), "..", "data", "reminders.json"
)

# ── Approximate prayer times ──────────────────────────────
#  Fixed for now. Location-aware times come with Muslim Identity system.
PRAYER_TIMES = {
    "fajr":    "05:30",
    "dhuhr":   "12:30",
    "asr":     "15:45",
    "maghrib": "18:30",
    "isha":    "20:00",
}

# ── What Gemini looks for in strict mode photos ───────────
#  Each task type has a specific verification prompt.
#  The more specific, the harder to cheat.
STRICT_PROMPTS = {
    "prayer":     "Does this image show a person praying, a prayer mat, or someone in an Islamic prayer position such as sujood or ruku? Answer YES or NO then explain in one sentence.",
    "gym":        "Does this image show a person at a gym, using gym equipment, or showing evidence of a workout such as workout clothes or weights? Answer YES or NO then explain in one sentence.",
    "medication": "Does this image show medication, pills, a medicine bottle, or a person taking medicine? Answer YES or NO then explain in one sentence.",
    "groceries":  "Does this image show groceries, a supermarket, shopping bags with food, or a person grocery shopping? Answer YES or NO then explain in one sentence.",
    "study":      "Does this image show a person studying, open books, handwritten notes, or a study desk with materials? Answer YES or NO then explain in one sentence.",
    "default":    "Does this image show clear evidence that a task has been completed? Look for any relevant activity. Answer YES or NO then explain in one sentence.",
}


# ── Persistence ───────────────────────────────────────────

def _ensure_data_dir():
    os.makedirs(os.path.dirname(REMINDERS_FILE), exist_ok=True)


def _load() -> list:
    _ensure_data_dir()
    if not os.path.exists(REMINDERS_FILE):
        return []
    try:
        with open(REMINDERS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []


def _save(reminders: list):
    _ensure_data_dir()
    with open(REMINDERS_FILE, "w") as f:
        json.dump(reminders, f, indent=2)


# ── Add reminders ─────────────────────────────────────────

def add_reminder(
    text: str,
    remind_at: str,
    strict: bool = False,
    task_type: str = "default",
    repeat: str = "none",
) -> dict:
    """
    Adds a new reminder.

    Parameters:
      text      — what to remind ("pray Maghrib", "take medication")
      remind_at — "HH:MM" for today, or "YYYY-MM-DD HH:MM" for specific date
      strict    — True means photo proof required via Gemini Vision
      task_type — picks the right Gemini verification prompt
      repeat    — "none" / "daily" / "weekly"
    """
    if len(remind_at) == 5:
        today = date.today().isoformat()
        remind_at_full = f"{today} {remind_at}:00"
    else:
        remind_at_full = remind_at

    reminder = {
        "id":         str(uuid.uuid4()),
        "text":       text,
        "remind_at":  remind_at_full,
        "strict":     strict,
        "task_type":  task_type,
        "repeat":     repeat,
        "status":     "pending",
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }

    reminders = _load()
    reminders.append(reminder)
    _save(reminders)

    if ENABLE_LOGS:
        tag = " [STRICT]" if strict else ""
        print(f"[Notifications] Set: '{text}' at {remind_at_full}{tag}")

    return reminder


def add_prayer_reminders():
    """
    Sets all 5 daily prayer reminders with strict mode on.
    Clears existing prayer reminders first to avoid duplicates.
    Called when user says "remind me of all prayers" or during setup.
    """
    reminders = [r for r in _load() if r.get("task_type") != "prayer"]
    _save(reminders)

    for name, time_str in PRAYER_TIMES.items():
        add_reminder(
            text=f"pray {name.capitalize()}",
            remind_at=time_str,
            strict=True,
            task_type="prayer",
            repeat="daily",
        )

    if ENABLE_LOGS:
        print("[Notifications] All 5 prayer reminders set.")


# ── Status management ─────────────────────────────────────

def get_pending() -> list:
    """Returns all pending reminders."""
    return [r for r in _load() if r["status"] == "pending"]


def mark_done(reminder_id: str):
    """Marks reminder as completed and reschedules if repeating."""
    reminders = _load()
    for r in reminders:
        if r["id"] == reminder_id:
            r["status"] = "done"
            r["completed_at"] = datetime.now().isoformat(timespec="seconds")
            if r.get("repeat") == "daily":
                reminders.append(_next_daily(r))
            elif r.get("repeat") == "weekly":
                reminders.append(_next_weekly(r))
            break
    _save(reminders)


def mark_overridden(reminder_id: str):
    """
    User manually overrides strict mode verification.
    Marks done without photo proof. Logged separately so
    Matter knows the user bypassed verification.
    """
    reminders = _load()
    for r in reminders:
        if r["id"] == reminder_id:
            r["status"] = "done"
            r["overridden"] = True
            r["completed_at"] = datetime.now().isoformat(timespec="seconds")
            if r.get("repeat") == "daily":
                reminders.append(_next_daily(r))
            break
    _save(reminders)
    if ENABLE_LOGS:
        print(f"[Notifications] {reminder_id} overridden by user.")


def _next_daily(reminder: dict) -> dict:
    """Creates tomorrow's copy of a daily reminder."""
    old_time = datetime.fromisoformat(reminder["remind_at"])
    new = reminder.copy()
    new["id"]         = str(uuid.uuid4())
    new["status"]     = "pending"
    new["remind_at"]  = (old_time + timedelta(days=1)).isoformat(timespec="seconds")
    new["created_at"] = datetime.now().isoformat(timespec="seconds")
    new.pop("completed_at", None)
    new.pop("overridden", None)
    return new


def _next_weekly(reminder: dict) -> dict:
    """Creates next week's copy of a weekly reminder."""
    old_time = datetime.fromisoformat(reminder["remind_at"])
    new = reminder.copy()
    new["id"]         = str(uuid.uuid4())
    new["status"]     = "pending"
    new["remind_at"]  = (old_time + timedelta(weeks=1)).isoformat(timespec="seconds")
    new["created_at"] = datetime.now().isoformat(timespec="seconds")
    new.pop("completed_at", None)
    return new


# ── Windows toast notification ────────────────────────────

def _send_toast(title: str, message: str):
    """
    Fires a Windows desktop toast notification.
    Requires: pip install win10toast
    Falls back to a print if not installed.

    Why win10toast over other methods? It's the simplest
    pure-Python way to fire a real Windows notification
    without needing a C extension or UWP app.
    """
    try:
        from win10toast import ToastNotifier  # type: ignore
        toaster = ToastNotifier()
        toaster.show_toast(
            title,
            message,
            duration=10,
            threaded=True,
        )
    except ImportError:
        print(f"\n[REMINDER] {title}: {message}\n")
    except Exception as e:
        if ENABLE_LOGS:
            print(f"[Notifications] Toast error: {e}")


# ── Strict mode — webcam capture ──────────────────────────

def _capture_photo() -> Optional[str]:
    """
    Captures a single frame from the webcam.
    Returns the image as a base64 string, or None if it fails.

    Why base64? Gemini Vision API expects images as base64
    encoded strings when sent inline with the request.
    We don't save the photo to disk — it goes straight to
    Gemini and is then discarded. Privacy matters.
    """
    try:
        import cv2
        cap = cv2.VideoCapture(0)

        if not cap.isOpened():
            if ENABLE_LOGS:
                print("[Notifications] Webcam not available.")
            return None

        # Give the camera a moment to warm up
        time.sleep(1.5)

        ret, frame = cap.read()
        cap.release()

        if not ret:
            return None

        # Encode frame to JPEG then base64
        _, buffer = cv2.imencode(".jpg", frame)
        b64 = base64.b64encode(buffer).decode("utf-8")

        if ENABLE_LOGS:
            print("[Notifications] Photo captured for verification.")

        return b64

    except ImportError:
        if ENABLE_LOGS:
            print("[Notifications] opencv-python not installed. pip install opencv-python")
        return None
    except Exception as e:
        if ENABLE_LOGS:
            print(f"[Notifications] Webcam error: {e}")
        return None


# ── Strict mode — Gemini Vision verification ──────────────

def verify_with_gemini(reminder: dict) -> tuple[bool, str]:
    """
    Captures a photo and asks Gemini Vision if the task is done.

    Returns:
      (True, explanation)  — if Gemini confirms completion
      (False, explanation) — if Gemini says not done
      (False, "no photo")  — if webcam failed

    How it works:
      1. Capture webcam frame as base64
      2. Pick the right verification prompt for this task type
      3. Send to Gemini with the image inline
      4. Parse the YES/NO from Gemini's response
    """
    photo_b64 = _capture_photo()

    if not photo_b64:
        return False, "Could not capture a photo. Please check your webcam."

    task_type = reminder.get("task_type", "default")
    prompt    = STRICT_PROMPTS.get(task_type, STRICT_PROMPTS["default"])

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=GEMINI_API_KEY)

        response = client.models.generate_content(
            model= GEMINI_MODEL,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part(
                            inline_data=types.Blob(
                                mime_type="image/jpeg",
                                data=base64.b64decode(photo_b64),
                            )
                        ),
                        types.Part(text=prompt),
                    ],
                )
            ],
        )

        reply = (response.text or "").strip()                                  
        verified = reply.upper().startswith("YES")

        if ENABLE_LOGS:
            print(f"[Notifications] Gemini verification: {reply}")

        return verified, reply

    except Exception as e:
        if ENABLE_LOGS:
            print(f"[Notifications] Gemini verification error: {e}")
        return False, "Verification failed. You can override manually."


# ── Notification engine ───────────────────────────────────

_engine_running = False


def _check_due(speaker, ui=None):
    """
    Checks all pending reminders and fires any that are due.
    Called every 60 seconds by the engine loop.

    For normal reminders: speak + toast.
    For strict reminders: speak + toast + Gemini verification loop.
    """
    now = datetime.now()
    pending = get_pending()

    for reminder in pending:
        try:
            due_time = datetime.fromisoformat(reminder["remind_at"])
        except Exception:
            continue

        # Fire if within the current minute
        diff = (now - due_time).total_seconds()
        if 0 <= diff < 60:
            _fire_reminder(reminder, speaker, ui)


def _fire_reminder(reminder: dict, speaker, ui=None):
    import main
    ui = main.ui 
    """
    Fires a single reminder — speaks it, toasts it,
    and handles strict mode verification if needed.
    """
    text = reminder["text"]
    is_strict = reminder.get("strict", False)

    if ENABLE_LOGS:
        print(f"[Notifications] FIRING: '{text}' | Strict: {is_strict}")

    # Speak it
    spoken = f"Sir, this is your reminder to {text}."
    if is_strict:
        spoken += " This is a strict reminder. I will need to verify completion."

    speaker.say(spoken)

    # Toast notification
    _send_toast(
        "MATTER — Reminder",
        f"{text}" + (" [STRICT MODE]" if is_strict else "")
    )

    # Log to UI if available
    if ui:
        try:
            getattr(ui, "log_system")(f"Reminder: {text}")
        except Exception:
            pass

    if not is_strict:
        # Normal reminder — just mark done
        mark_done(reminder["id"])
        return

    # ── Strict mode verification loop ────────────────────
    #  Matter gives the user 5 minutes to complete the task
    #  and send a photo. Checks every 60 seconds.
    #  After 5 failed checks, nags more insistently.

    def _strict_loop():
        attempts = 0
        max_attempts = 10   # 10 minutes total

        while attempts < max_attempts:
            time.sleep(60)  # Wait 1 minute before checking

            # Check if user already overrode it
            current = next(
                (r for r in _load() if r["id"] == reminder["id"]),
                None
            )
            if not current or current["status"] == "done":
                return

            attempts += 1
            speaker.say(
                f"Sir, I still need to verify that you have completed: {text}. "
                f"Please look at the camera."
            )

            time.sleep(3)  # Give them a moment to look at camera
            verified, explanation = verify_with_gemini(reminder)

            if verified:
                mark_done(reminder["id"])
                speaker.say(
                    f"Verified, Sir. I can see you have completed {text}. Well done."
                )
                if ui:
                    try:
                        getattr(ui, "log_system")(f"Strict verified: {text}")
                    except Exception:
                        pass
                return
            else:
                if attempts < 5:
                    speaker.say(
                        f"I could not verify {text}, Sir. "
                        f"Please complete the task and I will check again."
                    )
                else:
                    # Getting more insistent after 5 attempts
                    speaker.say(
                        f"Sir, you have still not completed {text}. "
                        f"This matters. Please do it now. "
                        f"You can also say 'override reminder' if you have already done it."
                    )

        # Max attempts reached
        speaker.say(
            f"Sir, I was unable to verify {text} after multiple attempts. "
            f"Please say 'override reminder' if you completed it, "
            f"or I will remind you again next time."
        )

    threading.Thread(target=_strict_loop, daemon=True).start()


# ── Public API ────────────────────────────────────────────

def start(speaker, ui=None):
    """
    Starts the notification engine.
    Checks every 60 seconds for due reminders.
    Call this from main.py during boot().

    Why 60 seconds? Reminders are set to the minute,
    so checking every 60 seconds is precise enough
    without hammering the CPU.
    """
    global _engine_running

    if _engine_running:
        return

    _engine_running = True

    def _loop():
        if ENABLE_LOGS:
            print("[Notifications] Engine started.")

        while _engine_running:
            try:
                _check_due(speaker, ui)
            except Exception as e:
                if ENABLE_LOGS:
                    print(f"[Notifications] Engine error: {e}")
            time.sleep(60)

    threading.Thread(target=_loop, daemon=True).start()


def stop():
    """Stops the notification engine."""
    global _engine_running
    _engine_running = False
    if ENABLE_LOGS:
        print("[Notifications] Engine stopped.")


def parse_reminder_from_voice(user_input: str) -> Optional[dict]:
    """
    Parses a voice command into reminder parameters.
    Called by detector when intent is 'set_reminder'.

    Examples:
      "remind me to pray Asr at 3:45pm" →
        text="pray Asr", time="15:45", strict=True, task_type="prayer"

      "remind me to go to the gym at 7am" →
        text="go to the gym", time="07:00", strict=True, task_type="gym"

      "remind me to call mum at 6pm" →
        text="call mum", time="18:00", strict=False, task_type="default"

    Returns a dict with parsed fields, or None if parsing fails.
    """
    import re
    text_lower = user_input.lower()

    # ── Detect task type and strict mode ──────────────────
    task_type = "default"
    strict    = False

    prayer_keywords = ["pray", "fajr", "dhuhr", "asr", "maghrib", "isha", "salah", "namaz"]
    gym_keywords    = ["gym", "workout", "exercise", "training", "run", "jog"]
    med_keywords    = ["medication", "medicine", "pill", "tablet", "dose"]
    grocery_keywords = ["groceries", "grocery", "shopping", "supermarket"]
    study_keywords  = ["study", "revision", "homework", "assignment"]

    if any(k in text_lower for k in prayer_keywords):
        task_type = "prayer"
        strict    = True
    elif any(k in text_lower for k in gym_keywords):
        task_type = "gym"
        strict    = True
    elif any(k in text_lower for k in med_keywords):
        task_type = "medication"
        strict    = True
    elif any(k in text_lower for k in grocery_keywords):
        task_type = "groceries"
        strict    = False   # Groceries don't need photo proof by default
    elif any(k in text_lower for k in study_keywords):
        task_type = "study"
        strict    = False

    # ── Extract time ──────────────────────────────────────
    # Matches patterns like "3:45pm", "7am", "15:30"
    time_match = re.search(
        r'\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b',
        text_lower
    )

    if not time_match:
        return None

    hour   = int(time_match.group(1))
    minute = int(time_match.group(2)) if time_match.group(2) else 0
    ampm   = time_match.group(3)

    if ampm == "pm" and hour != 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0

    time_str = f"{hour:02d}:{minute:02d}"

    # ── Extract reminder text ─────────────────────────────
    # Remove "remind me to", "at X:XXpm" etc. to get the core task
    reminder_text = text_lower
    for phrase in ["remind me to", "remind me about", "set a reminder to", "set a reminder for"]:
        reminder_text = reminder_text.replace(phrase, "").strip()

    # Remove the time part
    reminder_text = re.sub(r'\bat\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?\b', "", reminder_text).strip()

    if not reminder_text:
        return None

    return {
        "text":      reminder_text,
        "remind_at": time_str,
        "strict":    strict,
        "task_type": task_type,
        "repeat":    "none",
    }