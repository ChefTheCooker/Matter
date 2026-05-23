# ============================================================
#  MATTER — core/humanity/action_queue.py
#  Matter's conscience. Every proactive action passes through
#  here before anything happens.
#
#  Three tiers:
#    FREE       — Matter just does it. Logged, but no approval needed.
#    CHECK      — Queued. Matter asks you at the next interaction.
#    RESTRICTED — Never happens without an explicit voice command.
#
#  If you're ever unsure which tier something belongs in,
#  ask yourself: "Would I be annoyed if Matter did this without asking?"
#  Yes → CHECK. "Would it feel like a violation?" → RESTRICTED.
# ============================================================

import os
import json
from datetime import datetime, date
from enum import Enum

from core.config import ENABLE_LOGS

# ── Queue file location ───────────────────────────────────
QUEUE_FILE = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "action_queue.json"
)


# ── Tier definitions ──────────────────────────────────────

class Tier(str, Enum):
    FREE       = "free"        # Do it immediately, no questions asked
    CHECK      = "check"       # Queue it, ask at next interaction
    RESTRICTED = "restricted"  # Never without explicit permission


# ── Action type registry ──────────────────────────────────
#  Every action type Matter can take proactively.
#  Add new action types here as Humanity grows.
#
#  Why a registry? So the tier is defined once, centrally.
#  You never have to guess "is this a FREE or CHECK action?"
#  — it's always in this table.

ACTION_TIERS = {
    # FREE — no friction, Matter just does it
    "set_reminder":         Tier.FREE,
    "prep_workspace":       Tier.FREE,      # Open apps for a session
    "draft_note":           Tier.FREE,      # Write a note to show you later
    "log_entry":            Tier.FREE,      # Internal logging
    "queue_suggestion":     Tier.FREE,      # Queue a suggestion to show you

    # CHECK — queued, Matter asks before acting
    "send_message":         Tier.CHECK,     # Send a message on your behalf
    "reorganise_files":     Tier.CHECK,     # Move/rename files
    "schedule_event":       Tier.CHECK,     # Add to calendar
    "open_external_link":   Tier.CHECK,     # Navigate somewhere specific
    "post_online":          Tier.CHECK,     # Any posting to the internet

    # RESTRICTED — hard no without explicit voice command
    "spend_money":          Tier.RESTRICTED,
    "share_personal_data":  Tier.RESTRICTED,
    "access_passwords":     Tier.RESTRICTED,
    "delete_files":         Tier.RESTRICTED,
    "external_account":     Tier.RESTRICTED,  # Login to anything
    "camera_access":        Tier.RESTRICTED,
}


# ── Action structure ──────────────────────────────────────

def _make_action(action_type: str, description: str, payload: dict | None = None) -> dict:
    """
    Creates a standardised action dict.

    Parameters:
      action_type — must match a key in ACTION_TIERS
      description — human-readable explanation (what Matter will say to you)
      payload     — any extra data the executor needs to carry out the action

    The 'status' field tracks lifecycle:
      pending → done / dismissed / denied
    """
    return {
        "id":           _generate_id(),
        "type":         action_type,
        "tier":         ACTION_TIERS.get(action_type, Tier.CHECK).value,
        "description":  description,
        "payload":      payload or {},
        "created_at":   datetime.now().isoformat(timespec="seconds"),
        "status":       "pending",      # pending / done / dismissed / denied
        "resolved_at":  None,
    }


def _generate_id() -> str:
    """Simple timestamp-based ID. Unique enough for a queue."""
    return datetime.now().strftime("%Y%m%d%H%M%S%f")


# ── Queue persistence ─────────────────────────────────────

def _load_queue() -> list:
    """Loads the full queue from disk."""
    if not os.path.exists(QUEUE_FILE):
        return []
    try:
        with open(QUEUE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []


def _save_queue(queue: list):
    """Saves the full queue to disk."""
    os.makedirs(os.path.dirname(QUEUE_FILE), exist_ok=True)
    with open(QUEUE_FILE, "w") as f:
        json.dump(queue, f, indent=2)


# ── Public API ────────────────────────────────────────────

def submit(action_type: str, description: str, payload: dict | None = None) -> dict | None:
    """
    The main entry point. Submit a proposed action.

    What happens depends on the tier:
      FREE       → action is executed immediately (caller must handle execution)
                   and logged as 'done'
      CHECK      → action is added to the pending queue for the next interaction
      RESTRICTED → action is rejected immediately and logged as 'denied'

    Returns the action dict so the caller knows what happened.
    The caller checks action["tier"] to know whether to execute it.

    Usage:
      action = action_queue.submit(
          "set_reminder",
          "Remind you to drink water in 30 minutes",
          {"text": "drink water", "delay_minutes": 30}
      )
      if action and action["tier"] == Tier.FREE:
          # execute it
    """
    if action_type not in ACTION_TIERS:
        if ENABLE_LOGS:
            print(f"[ActionQueue] Unknown action type: '{action_type}'. Blocking.")
        return None

    tier = ACTION_TIERS[action_type]
    action = _make_action(action_type, description, payload)

    if tier == Tier.RESTRICTED:
        action["status"] = "denied"
        action["resolved_at"] = datetime.now().isoformat(timespec="seconds")
        if ENABLE_LOGS:
            print(f"[ActionQueue] RESTRICTED: '{action_type}' blocked. Requires explicit command.")
        _append_to_log(action)
        return action

    if tier == Tier.FREE:
        # The caller will execute it — we just mark it as done
        action["status"] = "done"
        action["resolved_at"] = datetime.now().isoformat(timespec="seconds")
        if ENABLE_LOGS:
            print(f"[ActionQueue] FREE: '{action_type}' approved immediately.")
        _append_to_log(action)
        return action

    if tier == Tier.CHECK:
        queue = _load_queue()
        queue.append(action)
        _save_queue(queue)
        if ENABLE_LOGS:
            print(f"[ActionQueue] CHECK: '{action_type}' queued for next interaction.")
        return action

    return None


def get_pending() -> list:
    """
    Returns all pending CHECK-tier actions.
    Called at the start of each interaction so Matter can ask about them.
    """
    queue = _load_queue()
    return [a for a in queue if a["status"] == "pending"]


def approve(action_id: str):
    """Marks a queued action as approved. Caller then executes it."""
    _update_status(action_id, "done")


def dismiss(action_id: str):
    """User said no. Action is dismissed and won't come up again."""
    _update_status(action_id, "dismissed")


def _update_status(action_id: str, status: str):
    queue = _load_queue()
    for action in queue:
        if action["id"] == action_id:
            action["status"] = status
            action["resolved_at"] = datetime.now().isoformat(timespec="seconds")
            break
    _save_queue(queue)


def _append_to_log(action: dict):
    """
    Appends a completed/denied action to a permanent history log.
    Separate from the queue — this is the audit trail.
    """
    log_file = os.path.join(
        os.path.dirname(QUEUE_FILE), "action_log.json"
    )
    log = []
    if os.path.exists(log_file):
        try:
            with open(log_file, "r") as f:
                log = json.load(f)
        except Exception:
            pass

    log.append(action)

    with open(log_file, "w") as f:
        json.dump(log, f, indent=2)


def count_pending() -> int:
    """Returns how many CHECK actions are waiting for approval."""
    return len(get_pending())


def clear_old_dismissed(days: int = 7):
    """
    Removes dismissed actions older than N days from the queue.
    Keeps the queue file from growing forever.
    """
    from datetime import timedelta
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    queue = _load_queue()
    queue = [
        a for a in queue
        if not (a["status"] == "dismissed" and a.get("resolved_at", "") < cutoff)
    ]
    _save_queue(queue)