# ============================================================
#  MATTER — ui/ui.py
#  Opens the Matter HTML UI in a standalone desktop window
#  using pywebview. No browser needed.
# ============================================================

import os
import webview


class MatterUI:

    def __init__(self):
        self._state  = "idle"
        self._log    = []
        self._window = None

        html_path = os.path.join(os.path.dirname(__file__), "MatterUI.htm")
        self._html_path = "file:///" + html_path.replace("\\", "/")

    # ── Launch ────────────────────────────────────────────

    def run(self):
        """
        Opens the Matter UI in a standalone desktop window.
        Call this on the main thread — blocks until window closes.
        """
        self._window = webview.create_window(
            title            = "MATTER — Personal AI System",
            url              = self._html_path,
            width            = 1400,
            height           = 800,
            resizable        = True,
            frameless        = False,
            background_color = "#010810",
        )
        webview.start()

    def quit(self):
        try:
            if self._window:
                self._window.destroy()
        except:
            pass
        os._exit(0)

    # ── State setters ─────────────────────────────────────

    def set_idle(self):
        self._state = "idle"
        self._js("setOrbState('idle')")

    def set_listening(self):
        self._state = "listening"
        self._js("setOrbState('listening')")

    def set_thinking(self):
        self._state = "thinking"
        self._js("setOrbState('thinking')")

    def set_speaking(self):
        self._state = "speaking"
        self._js("setOrbState('speaking')")

    # ── Logging ───────────────────────────────────────────

    def log_user(self, text: str):
        print(f"[YOU]    {text}")
        self._js(f"addLog('YOU','user',{repr(text)})")

    def log_matter(self, text: str):
        print(f"[MATTER] {text}")
        self._js(f"addLog('MATTER','matter',{repr(text)})")

    def log_system(self, text: str):
        print(f"[SYS]    {text}")
        self._js(f"addLog('SYS','sys',{repr(text)})")

    def update_device_count(self, count: int):
        print(f"[UI] Smart devices: {count}")
        self._js(f"document.getElementById('dev-count').textContent='{count}'")

    # ── JS bridge ─────────────────────────────────────────

    def _js(self, script: str):
        """Run JavaScript inside the webview window."""
        try:
            if self._window:
                self._window.evaluate_js(script)
        except Exception as e:
            print(f"[UI] JS error: {e}")
    def set_text_callback(self, fn):
        self._text_callback = fn

    def on_text_input(self, text: str):
        if hasattr(self, '_text_callback') and self._text_callback:
            self._text_callback(text)
