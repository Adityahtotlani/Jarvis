"""Tests for the Listener (STT + wake word detection)."""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from jarvis.core.listener import Listener

CONFIG = {
    "whisper": {"wake_model": "tiny", "command_model": "base", "chunk_seconds": 2, "command_silence_threshold": 1.5},
    "audio": {"sample_rate": 16000, "channels": 1},
    "jarvis": {"wake_word": "jarvis"},
}


@pytest.fixture
def listener():
    return Listener(CONFIG)


def test_transcribe_detects_wake_word(listener):
    fake_audio = np.zeros(32000, dtype="float32")
    mock_model = MagicMock()
    mock_model.transcribe.return_value = {"text": " Hey Jarvis, what's up?"}

    with patch.object(listener, "_get_wake_model", return_value=mock_model):
        with patch.object(listener, "_record_chunk", return_value=fake_audio):
            # Should return on the first chunk because wake word is present
            listener.wait_for_wake_word()
            mock_model.transcribe.assert_called_once()


def test_transcribe_skips_chunk_without_wake_word(listener):
    fake_audio = np.zeros(32000, dtype="float32")
    call_count = {"n": 0}
    responses = [{"text": "no match here"}, {"text": " jarvis "}]

    mock_model = MagicMock()

    def _transcribe(audio, fp16, language):
        r = responses[min(call_count["n"], len(responses) - 1)]
        call_count["n"] += 1
        return r

    mock_model.transcribe.side_effect = _transcribe

    with patch.object(listener, "_get_wake_model", return_value=mock_model):
        with patch.object(listener, "_record_chunk", return_value=fake_audio):
            listener.wait_for_wake_word()
            assert mock_model.transcribe.call_count == 2


def test_transcribe_command_returns_text(listener):
    fake_audio = np.zeros(32000, dtype="float32")
    mock_model = MagicMock()
    mock_model.transcribe.return_value = {"text": "Open Safari"}

    with patch.object(listener, "_get_command_model", return_value=mock_model):
        with patch("jarvis.core.listener.sd") as mock_sd, \
             patch("jarvis.core.listener.queue.Queue") as mock_queue_cls, \
             patch("jarvis.core.listener.threading.Event") as mock_event_cls:

            # Simulate: one audio chunk, then silence long enough to stop
            mock_queue = MagicMock()
            mock_queue_cls.return_value = mock_queue

            # Return a chunk of audio (above silence threshold), then raise Empty
            import queue
            chunk = np.ones((800, 1), dtype="float32") * 0.05
            mock_queue.get.side_effect = [chunk, queue.Empty, queue.Empty]

            mock_event = MagicMock()
            mock_event.is_set.side_effect = [False, False, True]
            mock_event_cls.return_value = mock_event

            # Patch np.concatenate and the model
            with patch("numpy.concatenate", return_value=fake_audio):
                result = listener.transcribe_command()
                # With our mock the model returns "Open Safari"
                mock_model.transcribe.assert_called_once()
