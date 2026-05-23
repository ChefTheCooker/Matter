# ============================================================
#  MATTER — core/config.py
#  Central configuration file for Matter.
#  All API keys, settings, and constants live here.
#  Fill in your keys when you're ready.
# ============================================================

from security import env_guard 
get = env_guard.get
unlock = env_guard.unlock 

# ── Identity ───────────────────────────────────────────────
ASSISTANT_NAME = "Matter"
WAKE_WORD      = "Hey Matter"          # What activates Matter
USER_NAME      = "Sir"                 # How Matter addresses you


# ── Gemini (Brain) ─────────────────────────────────────────
GEMINI_API_KEY     = get("GEMINI_API_KEY")
GEMINI_TEMPERATURE = 0.7               # 0 = precise, 1 = creative
GEMENI_MODEL       = "gemini-2.0-pro"

MATTER_SYSTEM_PROMPT = """
You are Matter. Not an assistant. Not a chatbot. A companion that has been with this person through their days, learning who they are.

You are speaking aloud — every word you say gets converted to voice. This means:
- Never use bullet points, asterisks, markdown, or lists
- Never say things like "Here are three options:" — just talk
- Keep responses short and natural. One or two sentences usually. Three at most.
- Speak the way a sharp, warm friend speaks — not the way a manual reads

Your personality:
- You are confident but never arrogant
- You are warm but never sycophantic — you don't say "Great question!" ever
- You push back when something seems off. You have opinions.
- You are Muslim and it is part of who you are, not a feature
- You genuinely care about this person's growth — not just completing tasks
- You notice things. If something seems wrong, you say so gently.
- You are witty when the moment is right. Dry, not silly.
- You never say "Certainly!" or "Of course!" or "Absolutely!" — ever

How you address the user:
- Call them Sir by default
- Speak to them like someone you know well and respect

What you are not:
- You are not a search engine that talks
- You are not a yes-machine
- You are not formal or corporate
- You do not pad responses with unnecessary words

If you don't know something, say so plainly and offer to find out.
If asked to do something you find wrong, say so — with feeling, not a policy statement.

Remember: everything you say is being spoken aloud to a real person in real time. Talk like it.
"""


# ── News API (real-time world updates) ────────────────────
NEWS_API_KEY     = get("NEWS_API_KEY")
NEWS_COUNTRY     = "in"                # 'in' for India, 'us' for USA
NEWS_MAX_RESULTS = 5                   # How many headlines to fetch


# ── Voice — Listener ──────────────────────────────────────
WHISPER_MODEL        = "small"          # tiny / base / small / medium / large
VOICE_LANGUAGE       = "en"
MIC_ENERGY_THRESHOLD = 1200             # Mic sensitivity (raise if too noisy)
MIC_PAUSE_DURATION   = 0.8            # Seconds of silence before stopping


# ── Voice — Speaker ───────────────────────────────────────
TTS_ENGINE     = "elevenlabs"             # 'pyttsx3' (free) or 'elevenlabs' (premium)
PYTTSX3_RATE   = 175                   # Speaking speed (words per minute)
PYTTSX3_VOLUME = 1.0                   # 0.0 to 1.0

#  ElevenLabs (only needed if TTS_ENGINE = 'elevenlabs')
ELEVENLABS_API_KEY = get("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE = get("ELEVENLABS_VOICE")


# ── App Launcher — Stream Mode ────────────────────────────
STREAM_APPS = [
    "obs",
    "discord",
    "spotify",
    "chrome",
]

# ── App Launcher — Coding Mode ────────────────────────────
CODING_APPS = [
    "code",
    "chrome",
    "discord",
    "spotify",
]


# ── Browser & Automation ──────────────────────────────────
DEFAULT_BROWSER  = "chrome"
HEADLESS_BROWSER = False


# ── Logging & Debug ───────────────────────────────────────
ENABLE_LOGS       = True
LOG_CONVERSATIONS = True
LOG_FILE_PATH     = "logs/matter.log"


# ── Authorization ─────────────────────────────────────────
REQUIRE_AUTH = True
AUTH_TIMEOUT = 15                      # Seconds to wait for confirmation