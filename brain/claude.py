# ============================================================
#  MATTER — brain/claude.py
#  The brain of Matter. Connects to Google Gemini API
#  and generates all of Matter's natural spoken responses.
# ============================================================

from google import genai
from google.genai import types
from core.config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    GEMINI_TEMPERATURE,
    MATTER_SYSTEM_PROMPT,
    ENABLE_LOGS,
)


# ── Initialise Gemini client ──────────────────────────────
client = genai.Client(api_key=GEMINI_API_KEY)

# ── Conversation memory ────────────────────────────────────
_history = []


def think(user_input: str , personality: str = "") -> str:
    """
    Main conversation function. Keeps full memory of the session.
    Everything the user says goes through here.
    """
    global _history

    if ENABLE_LOGS:
        print(f"[Brain] Thinking about: {user_input}")

    # Add user message to history
    full_input = f"[Bond context: {personality}]\n{user_input}" if personality else user_input

    _history.append(
        types.Content(role="user", parts=[types.Part(text=full_input)])
    )




    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=_history,
            config=types.GenerateContentConfig(
                system_instruction=MATTER_SYSTEM_PROMPT,
                temperature=GEMINI_TEMPERATURE,
            ),
        )
        reply = response.text.strip()

        # Save assistant reply to history
        _history.append(
            types.Content(role="model", parts=[types.Part(text=reply)])
        )

        if ENABLE_LOGS:
            print(f"[Brain] Matter says: {reply}")

        return reply

    except Exception as e:
        if ENABLE_LOGS:
            print(f"[Brain] Error: {e}")
        return "Sir, something went wrong on my end. Please try again."


def generate(prompt: str) -> str:
    """
    One-off generation with no memory.
    Used for confirmations and system messages.
    """
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=MATTER_SYSTEM_PROMPT,
                temperature=GEMINI_TEMPERATURE,
            ),
        )
        reply = response.text.strip()

        if ENABLE_LOGS:
            print(f"[Brain] Generated: {reply}")

        return reply

    except Exception as e:
        if ENABLE_LOGS:
            print(f"[Brain] Error: {e}")
        return "Sir, I encountered an unexpected issue. Please try again."


def clear_memory():
    """Wipes conversation history."""
    global _history
    _history = []
    if ENABLE_LOGS:
        print("[Brain] Conversation memory cleared.")


def memory_summary() -> str:
    return f"[Brain] {len(_history)} messages in current memory."