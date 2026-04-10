"""Text-to-speech for J.A.R.V.I.S.

Engine priority (highest quality first):
  1. ElevenLabs  — best quality; needs ELEVENLABS_API_KEY env var or config
  2. edge-tts    — Microsoft Neural TTS, free, no API key; `pip install edge-tts`
  3. macOS say   — built-in; defaults to "Daniel" (British male)
  4. espeak-ng   — Linux fallback
  5. espeak      — older Linux fallback
  6. none        — silent (all engines missing)

Recommended setup for the JARVIS voice:
  pip install edge-tts
  # engine auto-selects en-GB-RyanNeural — British male, authoritative
"""

import os
import platform
import shutil
import subprocess
import tempfile
import threading


# ---------------------------------------------------------------------------
# Audio player (used by edge-tts and ElevenLabs to play MP3 output)
# ---------------------------------------------------------------------------

def _play_mp3(path: str) -> None:
    """Play an MP3 file using the best available player."""
    if platform.system() == "Darwin":
        subprocess.run(["afplay", path], check=False, capture_output=True)
        return
    # Linux: try players in preference order
    for player, args in [
        ("mpg123",  ["-q", path]),
        ("ffplay",  ["-nodisp", "-autoexit", "-loglevel", "quiet", path]),
        ("mpg321",  [path]),
        ("cvlc",    ["--play-and-exit", "--quiet", path]),
    ]:
        if shutil.which(player):
            subprocess.run([player, *args], check=False, capture_output=True)
            return


# ---------------------------------------------------------------------------
# Engine detection
# ---------------------------------------------------------------------------

def _has_edge_tts() -> bool:
    try:
        import edge_tts  # noqa: F401
        return True
    except ImportError:
        return False


def _detect_engine(config: dict) -> str:
    tts_cfg = config.get("tts", {})
    forced = tts_cfg.get("engine", "auto")

    if forced != "auto":
        return forced

    # ElevenLabs — check for API key first
    api_key = (
        tts_cfg.get("elevenlabs_api_key")
        or os.environ.get("ELEVENLABS_API_KEY")
    )
    if api_key:
        return "elevenlabs"

    # edge-tts — best free option
    if _has_edge_tts():
        return "edge"

    # macOS built-in
    if platform.system() == "Darwin" and shutil.which("say"):
        return "say"

    # Linux espeak
    for binary in ("espeak-ng", "espeak"):
        if shutil.which(binary):
            return binary

    try:
        import pyttsx3  # noqa: F401
        return "pyttsx3"
    except ImportError:
        pass

    return "none"


# ---------------------------------------------------------------------------
# Speaker class
# ---------------------------------------------------------------------------

class Speaker:
    def __init__(self, config: dict):
        tts_cfg    = config.get("tts", {})
        jarvis_cfg = config.get("jarvis", {})

        self._engine: str = _detect_engine(config)
        self._lock = threading.Lock()

        # edge-tts settings
        self._edge_voice: str = tts_cfg.get("edge_voice", "en-GB-RyanNeural")
        self._edge_rate:  str = tts_cfg.get("edge_rate", "-8%")   # slightly slower = gravitas

        # macOS say settings
        self._say_voice: str  = tts_cfg.get("say_voice", jarvis_cfg.get("voice", "Daniel"))
        self._say_rate:  int  = jarvis_cfg.get("speech_rate", 165)

        # ElevenLabs settings
        self._el_key: str      = (tts_cfg.get("elevenlabs_api_key")
                                  or os.environ.get("ELEVENLABS_API_KEY", ""))
        self._el_voice_id: str = tts_cfg.get(
            "elevenlabs_voice_id",
            "pNInz6obpgDQGcFmaJgB",  # "Adam" — deep, authoritative
        )

        # espeak settings
        self._espeak_bin: str = self._engine if self._engine in ("espeak-ng", "espeak") else "espeak-ng"
        self._espeak_wpm: int = int(self._say_rate * 0.85)

        # pyttsx3
        self._pyttsx3_engine = None
        if self._engine == "pyttsx3":
            self._pyttsx3_engine = self._init_pyttsx3()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def engine_name(self) -> str:
        return self._engine

    def speak(self, text: str, blocking: bool = True) -> None:
        """Speak *text* using the best available engine."""
        if not text or self._engine == "none":
            return

        dispatch = {
            "edge":       self._speak_edge,
            "elevenlabs": self._speak_elevenlabs,
            "say":        self._speak_say,
            "pyttsx3":    self._speak_pyttsx3,
        }

        fn = dispatch.get(self._engine, self._speak_espeak)

        if blocking:
            fn(text)
        else:
            threading.Thread(target=fn, args=(text,), daemon=True).start()

    # ------------------------------------------------------------------
    # edge-tts  (Microsoft Neural — en-GB-RyanNeural ≈ JARVIS)
    # ------------------------------------------------------------------

    def _speak_edge(self, text: str) -> None:
        tmp = tempfile.mktemp(suffix=".mp3")
        try:
            import asyncio
            import edge_tts

            async def _generate() -> None:
                comm = edge_tts.Communicate(
                    text,
                    self._edge_voice,
                    rate=self._edge_rate,
                )
                await comm.save(tmp)

            # Run async generation in its own event loop (safe from any thread)
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(_generate())
            finally:
                loop.close()

            _play_mp3(tmp)
        except Exception:
            # Fallback to say if edge-tts fails
            self._speak_say(text)
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass

    # ------------------------------------------------------------------
    # ElevenLabs  (premium — best quality)
    # ------------------------------------------------------------------

    def _speak_elevenlabs(self, text: str) -> None:
        tmp = tempfile.mktemp(suffix=".mp3")
        try:
            import requests  # type: ignore

            resp = requests.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{self._el_voice_id}",
                headers={
                    "xi-api-key":   self._el_key,
                    "Content-Type": "application/json",
                },
                json={
                    "text":      text,
                    "model_id":  "eleven_multilingual_v2",
                    "voice_settings": {
                        "stability":        0.60,
                        "similarity_boost": 0.85,
                        "style":            0.15,
                        "use_speaker_boost": True,
                    },
                },
                timeout=15,
            )
            if resp.status_code == 200:
                with open(tmp, "wb") as f:
                    f.write(resp.content)
                _play_mp3(tmp)
            else:
                # Quota exceeded or auth error — fall back
                self._speak_edge(text)
        except Exception:
            self._speak_edge(text)
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass

    # ------------------------------------------------------------------
    # macOS say
    # ------------------------------------------------------------------

    def _speak_say(self, text: str) -> None:
        with self._lock:
            subprocess.run(
                ["say", "-v", self._say_voice, "-r", str(self._say_rate), text],
                check=False,
                capture_output=True,
            )

    # ------------------------------------------------------------------
    # espeak-ng / espeak
    # ------------------------------------------------------------------

    def _speak_espeak(self, text: str) -> None:
        with self._lock:
            subprocess.run(
                [self._espeak_bin, "-s", str(self._espeak_wpm), text],
                check=False,
                capture_output=True,
            )

    # ------------------------------------------------------------------
    # pyttsx3
    # ------------------------------------------------------------------

    def _init_pyttsx3(self):
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty("rate", self._say_rate)
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
