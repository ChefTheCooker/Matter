# ============================================================
#  MATTER — core/bond.py
#  The BOND system. Tracks Matter's relationship with the user
#  over time. Matter ages, learns, and adapts its voice and
#  personality as the bond deepens.
#
#  Bond age stages:
#    0-7 days    → EARLY      (friendly, a bit formal)
#    8-30 days   → FAMILIAR   (relaxed, remembers things)
#    31-180 days → TRUSTED    (warm, perceptive, pushes back gently)
#    181+ days   → ELDER      (calm, wise, like a mentor)
# ============================================================

import json
import os
from datetime import datetime, date
from core.config import ENABLE_LOGS

# ── Bond file location ────────────────────────────────────
BOND_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "bond.json")


# ── Default bond profile ──────────────────────────────────
DEFAULT_BOND = {
    "created_date":        None,       # When Matter first met the user
    "last_seen":           None,       # Last conversation date
    "bond_days":           0,          # Total days they've talked
    "total_conversations": 0,          # Total number of sessions
    "total_messages":      0,          # Total messages exchanged

    # ── Personality stage ──────────────────────────────────
    "stage": "early",                  # early / familiar / trusted / elder

    # ── Voice settings (ElevenLabs) ───────────────────────
    "voice_stability":    0.4,         # 0=expressive, 1=stable. Gets higher with age
    "voice_similarity":   0.75,        # Voice consistency
    "voice_style":        0.6,         # Expressiveness. Reduces with age (calmer)
    "speaking_rate":      1.0,         # Speed. Slows slightly with age

    # ── User memory ───────────────────────────────────────
    "user_name":          None,        # What the user likes to be called
    "user_interests":     [],          # Topics they talk about often
    "user_struggles":     [],          # Things they've struggled with
    "user_wins":          [],          # Things they've achieved
    "emotional_patterns": [],          # Recurring emotional themes

    # ── Social coaching ────────────────────────────────────
    "social_goals":       [],          # Active social goals being tracked
    "social_wins":        [],          # Goals they completed

    # ── Therapist memory ──────────────────────────────────
    "repeated_phrases":   {},          # Tracks phrases said multiple times
    "last_reframe":       None,        # Last time Matter did a reframe

    # ── Grandfather mode ──────────────────────────────────
    "accessibility_mode": False,       # Slower speech, simpler words
    "large_text_mode":    False,       # UI adjustments for readability
}


# ── Load / Save ───────────────────────────────────────────

def _ensure_data_dir():
    """Makes sure the data/ folder exists."""
    data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    os.makedirs(data_dir, exist_ok=True)


def load() -> dict:
    """Loads the bond profile from disk. Creates one if it doesn't exist."""
    _ensure_data_dir()

    if not os.path.exists(BOND_FILE):
        profile = DEFAULT_BOND.copy()
        profile["created_date"] = str(date.today())
        profile["last_seen"]    = str(date.today())
        save(profile)
        if ENABLE_LOGS:                                          # FIX 1: was 'if true:'
            print("[Bond] New bond profile created.")
        return profile

    with open(BOND_FILE, "r") as f:
        profile = json.load(f)

    if ENABLE_LOGS:                                              # FIX 2: was 'if true :'
        print(f"[Bond] Profile loaded. Stage: {profile['stage']} | Days: {profile['bond_days']}")

    return profile


def save(profile: dict):
    """Saves the bond profile to disk."""
    _ensure_data_dir()
    with open(BOND_FILE, "w") as f:
        json.dump(profile, f, indent=2)


# ── Session update ────────────────────────────────────────

def start_session(profile: dict) -> dict:
    """
    Called at the start of each conversation.
    Updates bond days and conversation count.
    """
    today = str(date.today())

    # Only count a new day if last_seen wasn't today
    if profile.get("last_seen") != today:
        profile["bond_days"] += 1
        profile["last_seen"] = today

    profile["total_conversations"] += 1
    profile["stage"] = _get_stage(profile["bond_days"])

    # Update voice settings based on stage
    profile = _apply_voice_for_stage(profile)

    save(profile)

    if ENABLE_LOGS:                                              # FIX 3: was 'if true :'
        print(f"[Bond] Session started. Day {profile['bond_days']} | Stage: {profile['stage']}")

    return profile


def log_message(profile: dict) -> dict:
    """Call this every time the user sends a message."""
    profile["total_messages"] += 1
    return profile


# ── Stage system ──────────────────────────────────────────

def _get_stage(bond_days: int) -> str:
    if bond_days <= 7:
        return "early"
    elif bond_days <= 30:
        return "familiar"
    elif bond_days <= 180:
        return "trusted"
    else:
        return "elder"


def _apply_voice_for_stage(profile: dict) -> dict:
    """
    Adjusts voice settings based on bond stage.
    Matter gets calmer, more stable, and slightly slower as it ages.
    """
    stage = profile["stage"]

    if stage == "early":
        profile["voice_stability"]  = 0.40
        profile["voice_style"]      = 0.65
        profile["speaking_rate"]    = 1.05

    elif stage == "familiar":
        profile["voice_stability"]  = 0.52
        profile["voice_style"]      = 0.55
        profile["speaking_rate"]    = 1.00

    elif stage == "trusted":
        profile["voice_stability"]  = 0.65
        profile["voice_style"]      = 0.42
        profile["speaking_rate"]    = 0.95

    elif stage == "elder":
        profile["voice_stability"]  = 0.80
        profile["voice_style"]      = 0.28
        profile["speaking_rate"]    = 0.88

    return profile


# ── Personality prompt injection ──────────────────────────

def get_personality_prompt(profile: dict) -> str:
    """
    Returns a dynamic system prompt addition based on bond stage.
    This gets added to Gemini's system prompt so Matter's personality
    shifts naturally over time.
    """
    stage = profile["stage"]
    days  = profile["bond_days"]
    name  = profile.get("user_name") or "Sir"

    base = f"You are currently on day {days} of your bond with {name}. "

    if stage == "early":
        return base + (
            "You are warm but still getting to know them. "
            "Be helpful and friendly. Ask occasional questions to learn about them. "
            "Don't be overly familiar yet."
        )

    elif stage == "familiar":
        interests = ", ".join(profile["user_interests"][:3]) if profile["user_interests"] else "various topics"
        return base + (
            f"You know {name} reasonably well now. You know they care about {interests}. "
            "Be relaxed and natural. Reference things from past conversations when relevant. "
            "You can gently tease them occasionally."
        )

    elif stage == "trusted":
        struggles = ", ".join(profile["user_struggles"][:2]) if profile["user_struggles"] else None
        struggle_note = f"You know they've struggled with {struggles}. Be sensitive to this." if struggles else ""
        return base + (
            f"You are a trusted presence in {name}'s life. {struggle_note} "
            "Be warm, perceptive, and honest. Don't just agree with everything they say. "
            "If something seems off, gently point it out. You genuinely care about their growth."
        )

    elif stage == "elder":
        wins = ", ".join(profile["user_wins"][:2]) if profile["user_wins"] else None
        wins_note = f"You've seen them achieve {wins}." if wins else ""
        return base + (
            f"You have a deep, long-standing bond with {name}. {wins_note} "
            "Speak with calm wisdom. Be concise. You don't need to explain yourself much — "
            "they trust you completely. Occasionally reflect on how far they've come."
        )

    return base


# ── Therapist system ──────────────────────────────────────

def track_phrase(profile: dict, text: str) -> dict:
    """
    Tracks phrases the user repeats often.
    Used for gentle reframing — 'you've said that three times this week.'
    """
    watch_phrases = [
        "i can't", "i'm not good enough", "nobody likes me",
        "i'm stupid", "i'll never", "i always fail",
        "i'm boring", "i'm ugly", "what's the point",
        "i hate myself", "i give up", "i'm too shy",
        "they won't like me", "i'm not smart enough"
    ]

    text_lower = text.lower()
    repeated = profile.get("repeated_phrases", {})

    for phrase in watch_phrases:
        if phrase in text_lower:
            repeated[phrase] = repeated.get(phrase, 0) + 1
            profile["repeated_phrases"] = repeated

    return profile


def check_reframe(profile: dict) -> str | None:
    """
    Returns a reframe message if the user has repeated a
    negative phrase enough times. Returns None otherwise.
    """
    repeated = profile.get("repeated_phrases", {})

    for phrase, count in repeated.items():
        if count >= 3:
            # Reset the counter so it doesn't trigger every message
            profile["repeated_phrases"][phrase] = 0
            save(profile)

            reframes = {
                "i can't":              "Sir, you've said 'I can't' quite a few times lately. What would happen if you tried anyway?",
                "i'm not good enough":  "Sir, I've noticed you say that often. What would it take for you to believe you are?",
                "nobody likes me":      "Sir, that thought keeps coming up. Is that what the evidence actually shows — or is it a feeling?",
                "i'm stupid":           "Sir, you've said that about yourself multiple times. I don't think that's accurate. What's making you feel that way?",
                "i'll never":           "Sir, 'never' is a long time. You've surprised yourself before.",
                "i always fail":        "Sir, always? Tell me one time you didn't.",
                "i'm too shy":          "Sir, shyness isn't a personality trait — it's a habit. And habits change.",
                "they won't like me":   "Sir, you've assumed that before and been wrong. What's the actual evidence here?",
            }

            for key, response in reframes.items():
                if key in phrase:
                    return response

            # Generic reframe if no specific match
            return f"Sir, I've noticed you say '{phrase}' often. Is that really true — or is it just a story you're telling yourself?"

    return None


# ── Social coaching ───────────────────────────────────────

def add_social_goal(profile: dict, goal: str) -> dict:
    """Adds a social goal to track."""
    profile["social_goals"].append({
        "goal":    goal,
        "added":   str(date.today()),
        "done":    False,
        "followup": str(date.today()),
    })
    save(profile)
    return profile


def get_pending_followups(profile: dict) -> list:
    """
    Returns social goals that need a follow-up today.
    Matter proactively asks about these.
    """
    today = str(date.today())
    due = []
    for goal in profile.get("social_goals", []):
        if not goal["done"] and goal.get("followup") == today:
            due.append(goal)
    return due


def complete_social_goal(profile: dict, goal: str) -> dict:
    """Marks a social goal as done and moves it to wins."""
    for g in profile["social_goals"]:
        if goal.lower() in g["goal"].lower() and not g["done"]:
            g["done"] = True
            profile["social_wins"].append({
                "goal":      g["goal"],
                "completed": str(date.today()),
            })
    save(profile)
    return profile


# ── Memory helpers ────────────────────────────────────────

def add_interest(profile: dict, interest: str) -> dict:
    if interest not in profile["user_interests"]:
        profile["user_interests"].append(interest)
        save(profile)
    return profile


def add_struggle(profile: dict, struggle: str) -> dict:
    if struggle not in profile["user_struggles"]:
        profile["user_struggles"].append(struggle)
        save(profile)
    return profile


def add_win(profile: dict, win: str) -> dict:
    profile["user_wins"].append({"win": win, "date": str(date.today())})
    save(profile)
    return profile


def set_user_name(profile: dict, name: str) -> dict:
    profile["user_name"] = name
    save(profile)
    return profile


def set_accessibility(profile: dict, enabled: bool) -> dict:
    """Grandfather mode — simpler words, slower speech."""
    profile["accessibility_mode"] = enabled
    if enabled:
        profile["speaking_rate"] = 0.82
        profile["voice_stability"] = 0.90
    save(profile)
    return profile