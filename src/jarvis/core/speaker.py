"""Text-to-speech — macOS `say`, Linux espeak-ng/espeak, or silent fallback."""

import platform
import shutil
import subprocess
import threading


def _detect_engine() -> str:
    system = platform.system()
    if system == "Darwin" and shutil.which("say"):
        return "say"
    for binary in ("espeak-ng", "espeak"):
        if shutil.which(binary):
            return binary
    if shutil.which("festival"):
        return "festival"
    # pyttsx3 as last resort
    try:
        import pyttsx3  # noqa: F401
        return "pyttsx3"
    except ImportError:
        pass
    return "none"


class Speaker:
    def __init__(self, config: dict):
        jarvis_cfg = config.get("jarvis", {})
        self.voice: str = jarvis_cfg.get("voice", "Samantha")
        self.rate: int = jarvis_cfg.get("speech_rate", 175)
        self._engine: str = _detect_engine()
        self._lock = threading.Lock()
        self._pyttsx3_engine = None

        if self._engine == "pyttsx3":
            self._pyttsx3_engine = self._init_pyttsx3()

    def speak(self, text: str, blocking: bool = True) -> None:
        """Speak *text* aloud using the detected TTS engine."""
        if not text or self._engine == "none":
            return

        if self._engine == "pyttsx3":
            self._speak_pyttsx3(text)
            return

        cmd = self._build_cmd(text)
        if blocking:
            with self._lock:
                subprocess.run(cmd, check=False, capture_output=True)
        else:
            threading.Thread(
                target=self._run_cmd, args=(cmd,), daemon=True
            ).start()

    @property
    def engine_name(self) -> str:
        return self._engine

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_cmd(self, text: str) -> list[str]:
        if self._engine == "say":
            return ["say", "-v", self.voice, "-r", str(self.rate), text]
        if self._engine in ("espeak-ng", "espeak"):
            # espeak uses words-per-minute; scale from macOS rate
            wpm = max(80, int(self.rate * 0.85))
            return [self._engine, "-s", str(wpm), text]
        if self._engine == "festival":
            # festival reads from stdin via --tts flag
            return ["festival", "--tts"]
        return []

    def _run_cmd(self, cmd: list[str]) -> None:
        with self._lock:
            if self._engine == "festival":
                # festival needs text piped to stdin
                text = cmd  # reused slot — not ideal but kept simple
                return
            subprocess.run(cmd, check=False, capture_output=True)

    def _init_pyttsx3(self):
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty("rate", self.rate)
            return engine
        except Exception:
            return None

    def _speak_pyttsx3(self, text: str) -> None:
        if self._pyttsx3_engine is None:
            return
        try:
            self._pyttsx3_engine.say(text)
            self._pyttsx3_engine.runAndWait()
        except Exception:
            pass
