"""Tests for web_search and system_control skills."""

from unittest.mock import MagicMock, patch

import pytest

from jarvis.skills import system_control, web_search


# ── web_search ─────────────────────────────────────────────────────────────

def test_search_returns_text():
    mock_results = [
        {"body": "New York weather is sunny."},
        {"body": "Temperatures around 75F."},
        {"body": "Low humidity expected."},
    ]
    with patch("jarvis.skills.web_search.DDGS") as mock_ddgs_cls:
        mock_ddgs = MagicMock()
        mock_ddgs.__enter__ = MagicMock(return_value=mock_ddgs)
        mock_ddgs.__exit__ = MagicMock(return_value=False)
        mock_ddgs.text.return_value = iter(mock_results)
        mock_ddgs_cls.return_value = mock_ddgs

        result = web_search.search("weather New York")
        assert "New York" in result
        assert "sunny" in result


def test_search_no_results():
    with patch("jarvis.skills.web_search.DDGS") as mock_ddgs_cls:
        mock_ddgs = MagicMock()
        mock_ddgs.__enter__ = MagicMock(return_value=mock_ddgs)
        mock_ddgs.__exit__ = MagicMock(return_value=False)
        mock_ddgs.text.return_value = iter([])
        mock_ddgs_cls.return_value = mock_ddgs

        result = web_search.search("xyzzy nonsense query")
        assert "couldn't find" in result.lower()


# ── system_control ──────────────────────────────────────────────────────────

def test_open_app_success():
    with patch("jarvis.skills.system_control.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = system_control.open_app("Safari")
        mock_run.assert_called_once_with(["open", "-a", "Safari"], capture_output=True, text=True)
        assert "Opening Safari" in result


def test_open_app_failure():
    with patch("jarvis.skills.system_control.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1)
        result = system_control.open_app("FakeApp")
        assert "couldn't open" in result.lower()


def test_set_volume_clamps():
    with patch("jarvis.skills.system_control.subprocess.run") as mock_run:
        result = system_control.set_volume(150)
        call_args = mock_run.call_args[0][0]
        assert "100" in " ".join(call_args)
        assert "100" in result

        result = system_control.set_volume(-10)
        call_args = mock_run.call_args[0][0]
        assert "0" in " ".join(call_args)


def test_run_command_blocks_injection():
    result = system_control.run_command("ls; rm -rf /")
    assert "unsafe" in result.lower()

    result = system_control.run_command("cat file | grep secret")
    assert "unsafe" in result.lower()


def test_run_command_success():
    with patch("jarvis.skills.system_control.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="hello world", stderr="", returncode=0)
        result = system_control.run_command("echo hello world")
        assert "hello" in result
