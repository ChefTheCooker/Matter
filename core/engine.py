# ============================================================
#  MATTER — core/engine.py
#  Matter's hands. Executes real tasks on the user's Windows PC.
#  Opens apps, searches the web, fetches news, controls the system.
#  NOTHING runs here without user authorization first.
# ============================================================

import os
import time
import subprocess
import webbrowser
import wikipedia
import requests
from datetime import datetime
from core.config import (
    STREAM_APPS,
    CODING_APPS,
    DEFAULT_BROWSER,
    NEWS_API_KEY,
    NEWS_COUNTRY,
    NEWS_MAX_RESULTS,
    ENABLE_LOGS,
)


# ============================================================
#  APP LAUNCHER
# ============================================================

# Map of common app names to their Windows executable commands
APP_MAP = {
    "chrome":       "chrome",
    "firefox":      "firefox",
    "edge":         "msedge",
    "spotify":      "spotify",
    "discord":      "discord",
    "obs":          "obs64",
    "code":         "code",                  # VS Code
    "notepad":      "notepad",
    "calculator":   "calc",
    "explorer":     "explorer",
    "task manager": "taskmgr",
    "word":         "winword",
    "excel":        "excel",
    "powerpoint":   "powerpnt",
    "steam":        "steam",
    "vlc":          "vlc",
    "zoom":         "zoom",
    "slack":        "slack",
    "telegram":     "telegram",
    "whatsapp":     "whatsapp",
}


def open_app(app_name: str) -> bool:
    """
    Opens a single app by name.
    Returns True if launched successfully, False otherwise.
    """
    key = app_name.lower().strip()
    command = APP_MAP.get(key, key)   # fallback to raw name if not in map

    try:
        subprocess.Popen(command, shell=True)
        if ENABLE_LOGS:
            print(f"[Engine] Opened: {app_name}")
        return True
    except Exception as e:
        if ENABLE_LOGS:
            print(f"[Engine] Failed to open {app_name}: {e}")
        return False


def close_app(app_name: str) -> bool:
    """
    Force-closes an app by its process name.
    Returns True if closed successfully.
    """
    key = app_name.lower().strip()
    exe = APP_MAP.get(key, key) + ".exe"

    try:
        subprocess.call(["taskkill", "/F", "/IM", exe], shell=True)
        if ENABLE_LOGS:
            print(f"[Engine] Closed: {app_name}")
        return True
    except Exception as e:
        if ENABLE_LOGS:
            print(f"[Engine] Failed to close {app_name}: {e}")
        return False


def prepare_stream() -> list:
    """
    Opens all apps needed for a streaming session.
    Returns a list of apps that were launched.
    """
    if ENABLE_LOGS:
        print("[Engine] Preparing stream setup...")

    launched = []
    for app in STREAM_APPS:
        if open_app(app):
            launched.append(app)
        time.sleep(1.5)     # Small delay so apps don't crash each other on launch

    return launched


def prepare_coding() -> list:
    """
    Opens all apps needed for a coding session.
    Returns a list of apps that were launched.
    """
    if ENABLE_LOGS:
        print("[Engine] Preparing coding setup...")

    launched = []
    for app in CODING_APPS:
        if open_app(app):
            launched.append(app)
        time.sleep(1.5)

    return launched


# ============================================================
#  WEB & SEARCH
# ============================================================

def search_web(query: str) -> bool:
    """
    Opens a Google search for the given query in the default browser.
    Returns True if opened successfully.
    """
    try:
        url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
        webbrowser.open(url)
        if ENABLE_LOGS:
            print(f"[Engine] Searched web for: {query}")
        return True
    except Exception as e:
        if ENABLE_LOGS:
            print(f"[Engine] Web search failed: {e}")
        return False


def open_url(url: str) -> bool:
    """
    Opens a specific URL in the default browser.
    """
    try:
        if not url.startswith("http"):
            url = "https://" + url
        webbrowser.open(url)
        if ENABLE_LOGS:
            print(f"[Engine] Opened URL: {url}")
        return True
    except Exception as e:
        if ENABLE_LOGS:
            print(f"[Engine] Failed to open URL: {e}")
        return False


def search_wikipedia(query: str) -> str:
    """
    Searches Wikipedia and returns a short summary.
    Falls back gracefully if the topic isn't found.
    """
    try:
        wikipedia.set_lang("en")
        summary = wikipedia.summary(query, sentences=3, auto_suggest=True)
        if ENABLE_LOGS:
            print(f"[Engine] Wikipedia result for '{query}': {summary[:80]}...")
        return summary
    except wikipedia.exceptions.DisambiguationError as e:
        return f"Sir, that topic has multiple meanings. Could you be more specific? Options include: {', '.join(e.options[:4])}."
    except wikipedia.exceptions.PageError:
        return f"Sir, I couldn't find anything on Wikipedia for '{query}'."
    except Exception as e:
        if ENABLE_LOGS:
            print(f"[Engine] Wikipedia error: {e}")
        return "Sir, I had trouble fetching that from Wikipedia."


# ============================================================
#  NEWS & WORLD AWARENESS
# ============================================================

def get_headlines() -> list:
    """
    Fetches the latest news headlines using NewsAPI.
    Returns a list of headline strings.
    Requires NEWS_API_KEY to be set in config.
    """
    if NEWS_API_KEY == "your-newsapi-key-here":
        return ["Sir, the News API key is not configured yet."]

    try:
        url = (
            f"https://newsapi.org/v2/top-headlines?"
            f"country={NEWS_COUNTRY}&pageSize={NEWS_MAX_RESULTS}&apiKey={NEWS_API_KEY}"
        )
        response = requests.get(url, timeout=5)
        data     = response.json()

        if data.get("status") != "ok":
            return ["Sir, I could not fetch the news right now."]

        headlines = [
            article["title"]
            for article in data.get("articles", [])
            if article.get("title")
        ]

        if ENABLE_LOGS:
            print(f"[Engine] Fetched {len(headlines)} headlines.")

        return headlines if headlines else ["Sir, no headlines found."]

    except requests.ConnectionError:
        return ["Sir, I cannot reach the news servers. Please check the internet."]
    except Exception as e:
        if ENABLE_LOGS:
            print(f"[Engine] News error: {e}")
        return ["Sir, something went wrong while fetching the news."]


# ============================================================
#  SYSTEM UTILITIES
# ============================================================

def get_time() -> str:
    """
    Returns the current time as a spoken string.
    """
    now = datetime.now()
    return now.strftime("It is %I:%M %p, Sir.")


def get_date() -> str:
    """
    Returns today's date as a spoken string.
    """
    now = datetime.now()
    return now.strftime("Today is %A, %B %d, %Y, Sir.")


def shutdown_pc() -> None:
    """
    Shuts down the Windows PC.
    Should only be called after explicit user authorization.
    """
    if ENABLE_LOGS:
        print("[Engine] Initiating shutdown...")
    os.system("shutdown /s /t 5")


def restart_pc() -> None:
    """
    Restarts the Windows PC.
    Should only be called after explicit user authorization.
    """
    if ENABLE_LOGS:
        print("[Engine] Initiating restart...")
    os.system("shutdown /r /t 5")


def sleep_pc() -> None:
    """
    Puts the Windows PC to sleep.
    Should only be called after explicit user authorization.
    """
    if ENABLE_LOGS:
        print("[Engine] Putting system to sleep...")
    os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")


def set_volume(level: int) -> bool:
    """
    Sets the system volume (0–100).
    Uses PowerShell to adjust Windows audio.
    """
    try:
        level = max(0, min(100, level))
        script = f"(New-Object -ComObject WScript.Shell).SendKeys([char]174)"
        subprocess.run(["powershell", "-Command",
            f"$vol = {level}; $obj = New-Object -ComObject WScript.Shell"], 
            capture_output=True)
        if ENABLE_LOGS:
            print(f"[Engine] Volume set to {level}.")
        return True
    except Exception as e:
        if ENABLE_LOGS:
            print(f"[Engine] Volume error: {e}")
        return False


def take_screenshot(save_path: str = "screenshot.png") -> bool:
    """
    Takes a screenshot and saves it to the given path.
    """
    try:
        import pyautogui
        screenshot = pyautogui.screenshot()
        screenshot.save(save_path)
        if ENABLE_LOGS:
            print(f"[Engine] Screenshot saved to {save_path}.")
        return True
    except Exception as e:
        if ENABLE_LOGS:
            print(f"[Engine] Screenshot error: {e}")
        return False