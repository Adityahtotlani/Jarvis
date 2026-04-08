"""Text-to-speech using the macOS built-in `say` command."""

import subprocess
import threading


class Speaker:
    def __init__(self, config: dict):
        jarvis_cfg = config.get("jarvis", {})
        self.voice: str = jarvis_cfg.get("voice", "Samantha")
        self.rate: int = jarvis_cfg.get("speech_rate", 175)
        self._lock = threading.Lock()

    def speak(self, text: str, blocking: bool = True) -> None:
        """Speak the given text aloud."""
        if not text:
            return
        cmd = ["say", "-v", self.voice, "-r", str(self.rate), text]
        if blocking:
            with self._lock:
                subprocess.run(cmd, check=False)
        else:
            threading.Thread(target=self._run, args=(cmd,), daemon=True).start()

    def _run(self, cmd: list) -> None:
        with self._lock:
            subprocess.run(cmd, check=False)
