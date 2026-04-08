"""Global keyboard shortcut listener.

Listens for a configurable hotkey (default: Cmd+Shift+J) and sets a
threading.Event that main.py polls to bypass the wake-word path.
"""

import threading
from pynput import keyboard


class HotkeyListener:
    def __init__(self, config: dict, trigger_event: threading.Event):
        jarvis_cfg = config.get("jarvis", {})
        self.hotkey_combo: str = jarvis_cfg.get("hotkey", "<cmd>+<shift>+j")
        self._trigger_event = trigger_event
        self._listener: keyboard.GlobalHotKeys | None = None

    def _on_activate(self) -> None:
        self._trigger_event.set()

    def start(self) -> None:
        """Start the global hotkey listener in a background daemon thread."""
        self._listener = keyboard.GlobalHotKeys(
            {self.hotkey_combo: self._on_activate}
        )
        self._listener.daemon = True
        self._listener.start()

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
