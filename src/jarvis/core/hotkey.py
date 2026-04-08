"""Global keyboard shortcut listener.

Listens for a configurable hotkey (default: Cmd+Shift+J) and sets a
threading.Event that main.py polls to bypass the wake-word path.
"""

import threading
import time

from pynput import keyboard


class HotkeyListener:
    def __init__(self, config: dict, trigger_event: threading.Event):
        jarvis_cfg = config.get("jarvis", {})
        self.hotkey_combo: str = jarvis_cfg.get("hotkey", "<cmd>+<shift>+j")
        self._trigger_event = trigger_event
        self._listener: keyboard.GlobalHotKeys | None = None
        self._available = False

    def _on_activate(self) -> None:
        self._trigger_event.set()

    def start(self) -> None:
        """Start the global hotkey listener in a background daemon thread."""
        try:
            self._listener = keyboard.GlobalHotKeys(
                {self.hotkey_combo: self._on_activate}
            )
            self._listener.daemon = True
            self._listener.start()
            # Give it a moment to fail fast if permissions are missing
            time.sleep(0.3)
            self._available = True
            print(f"[Jarvis] Hotkey active: {self.hotkey_combo}")
        except Exception as e:
            print(f"[Jarvis] Hotkey unavailable ({e}). Wake word still works.")
            self._listener = None

    def stop(self) -> None:
        if self._listener:
            try:
                self._listener.stop()
            except Exception:
                pass
