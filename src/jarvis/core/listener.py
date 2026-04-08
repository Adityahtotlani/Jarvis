"""Microphone capture, wake-word detection, and speech-to-text via Whisper."""

import queue
import threading
import time

import numpy as np
import sounddevice as sd
import whisper


class Listener:
    def __init__(self, config: dict):
        whisper_cfg = config.get("whisper", {})
        audio_cfg = config.get("audio", {})
        jarvis_cfg = config.get("jarvis", {})

        self.sample_rate: int = audio_cfg.get("sample_rate", 16000)
        self.channels: int = audio_cfg.get("channels", 1)
        self.chunk_seconds: float = whisper_cfg.get("chunk_seconds", 2)
        self.silence_threshold: float = whisper_cfg.get("command_silence_threshold", 1.5)
        self.wake_word: str = jarvis_cfg.get("wake_word", "jarvis").lower()

        self._wake_model = None
        self._command_model = None
        self._wake_model_name: str = whisper_cfg.get("wake_model", "tiny")
        self._command_model_name: str = whisper_cfg.get("command_model", "base")

    # ------------------------------------------------------------------
    # Lazy model loading
    # ------------------------------------------------------------------

    def _get_wake_model(self):
        if self._wake_model is None:
            self._wake_model = whisper.load_model(self._wake_model_name)
        return self._wake_model

    def _get_command_model(self):
        if self._command_model is None:
            self._command_model = whisper.load_model(self._command_model_name)
        return self._command_model

    # ------------------------------------------------------------------
    # Audio helpers
    # ------------------------------------------------------------------

    def _record_chunk(self, duration: float) -> np.ndarray:
        """Record a fixed-length audio chunk from the microphone."""
        samples = int(self.sample_rate * duration)
        audio = sd.rec(
            samples,
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="float32",
        )
        sd.wait()
        return audio.flatten()

    def _transcribe(self, audio: np.ndarray, model) -> str:
        if audio is None or audio.size == 0:
            return ""
        # Ensure float32 and strip any NaN/inf from bad mic reads
        audio = np.nan_to_num(audio.astype(np.float32), nan=0.0, posinf=0.0, neginf=0.0)
        # Skip if silent or corrupted (mic permission denied)
        rms = float(np.sqrt(np.mean(audio ** 2)))
        if rms < 1e-6 or np.isnan(rms):
            return ""
        try:
            result = model.transcribe(audio, fp16=False, language="en")
            return result.get("text", "").strip().lower()
        except (ValueError, RuntimeError):
            # Corrupted audio causes NaN logits in Whisper — skip silently
            return ""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def wait_for_wake_word(self) -> None:
        """Block until the wake word is detected in the microphone stream."""
        model = self._get_wake_model()
        while True:
            audio = self._record_chunk(self.chunk_seconds)
            text = self._transcribe(audio, model)
            if self.wake_word in text:
                return

    def transcribe_command(self) -> str:
        """
        Record until the user stops speaking (silence detected), then
        return the transcribed command text.
        """
        model = self._get_command_model()
        audio_queue: queue.Queue = queue.Queue()
        stop_event = threading.Event()

        def _audio_callback(indata, frames, time_info, status):
            audio_queue.put(indata.copy())

        chunks = []
        silence_start = None

        with sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="float32",
            blocksize=int(self.sample_rate * 0.5),
            callback=_audio_callback,
        ):
            while not stop_event.is_set():
                try:
                    chunk = audio_queue.get(timeout=0.1)
                except queue.Empty:
                    continue

                chunks.append(chunk)
                rms = float(np.sqrt(np.mean(chunk ** 2)))

                if rms < 0.01:  # silence threshold (RMS)
                    if silence_start is None:
                        silence_start = time.monotonic()
                    elif time.monotonic() - silence_start >= self.silence_threshold:
                        stop_event.set()
                else:
                    silence_start = None

        if not chunks:
            return ""

        audio = np.concatenate(chunks).flatten()
        return self._transcribe(audio, model)
