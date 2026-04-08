"""Tests for Brain — LLM responses and tool routing."""

from unittest.mock import MagicMock, patch

import pytest

from jarvis.core.brain import Brain
from jarvis.memory.conversation import ConversationMemory

CONFIG = {
    "ollama": {"model": "llama3", "host": "http://localhost:11434", "context_turns": 5},
    "memory": {"db_path": ":memory:"},
}


@pytest.fixture
def memory(tmp_path):
    cfg = {"memory": {"db_path": str(tmp_path / "test.db")}}
    return ConversationMemory(cfg)


@pytest.fixture
def brain(memory):
    with patch("jarvis.core.brain.ollama.Client"):
        return Brain(CONFIG, memory)


def _mock_chat(brain, response_text):
    brain._client.chat.return_value = {"message": {"content": response_text}}


def test_plain_response(brain):
    _mock_chat(brain, "I am Jarvis, your AI assistant.")
    result = brain.process("Who are you?")
    assert "Jarvis" in result


def test_search_routing(brain):
    _mock_chat(brain, "[SEARCH: weather in New York]")
    with patch("jarvis.core.brain.web_search.search", return_value="It is sunny.") as mock_search:
        # Second LLM call for summarisation
        brain._client.chat.side_effect = [
            {"message": {"content": "[SEARCH: weather in New York]"}},
            {"message": {"content": "It is sunny in New York today."}},
        ]
        result = brain.process("What's the weather in New York?")
        mock_search.assert_called_once_with("weather in New York")
        assert "sunny" in result.lower()


def test_open_app_routing(brain):
    _mock_chat(brain, "[OPEN: Safari]")
    with patch("jarvis.core.brain.system_control.open_app", return_value="Opening Safari.") as mock_open:
        result = brain.process("Open Safari")
        mock_open.assert_called_once_with("Safari")
        assert "Opening Safari" in result


def test_volume_routing(brain):
    _mock_chat(brain, "[VOLUME: 50]")
    with patch("jarvis.core.brain.system_control.set_volume", return_value="Volume set to 50 percent.") as mock_vol:
        result = brain.process("Set volume to 50")
        mock_vol.assert_called_once_with(50)
        assert "50" in result


def test_cmd_routing(brain):
    _mock_chat(brain, "[CMD: ls /tmp]")
    with patch("jarvis.core.brain.system_control.run_command", return_value="file1.txt") as mock_cmd:
        result = brain.process("List files in tmp")
        mock_cmd.assert_called_once_with("ls /tmp")
        assert "file1" in result


def test_memory_context_included(brain, memory):
    memory.add_message("user", "My name is Tony.")
    memory.add_message("assistant", "Got it, Tony.")
    _mock_chat(brain, "Your name is Tony.")
    brain.process("What is my name?")
    call_args = brain._client.chat.call_args
    messages = call_args[1]["messages"] if "messages" in call_args[1] else call_args[0][1]
    contents = [m["content"] for m in messages]
    assert any("Tony" in c for c in contents)
