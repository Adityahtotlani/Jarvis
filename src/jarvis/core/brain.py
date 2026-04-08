"""Jarvis brain — Ollama LLM with tool routing and memory context."""

import re

import ollama

from jarvis.memory.conversation import ConversationMemory
from jarvis.skills import system_control, web_search

_SYSTEM_PROMPT = """\
You are Jarvis, a highly capable AI assistant modelled after the Iron Man AI.
Speak concisely — your responses will be read aloud, so avoid markdown, bullet
points, or long lists. Use plain sentences.

IMPORTANT: For any action request, you MUST respond with ONLY the tag — no extra words.

Actions and their tags:
  - Open an app by name (Chrome, Safari, Spotify, etc.) → [OPEN: <exact app name>]
  - Open a website or URL                               → [URL: <full url>]
  - Search the web                                      → [SEARCH: <query>]
  - Set the volume (0-100)                              → [VOLUME: <number>]
  - Run a terminal command                              → [CMD: <command>]

Examples:
  User: "open chrome"          → [OPEN: Google Chrome]
  User: "open youtube"         → [URL: https://www.youtube.com]
  User: "search the weather"   → [SEARCH: current weather]
  User: "set volume to 50"     → [VOLUME: 50]

For questions and conversation, respond naturally as Jarvis."""

_SEARCH_RE = re.compile(r"\[SEARCH:\s*(.+?)\]", re.IGNORECASE)
_OPEN_RE = re.compile(r"\[OPEN:\s*(.+?)\]", re.IGNORECASE)
_URL_RE = re.compile(r"\[URL:\s*(.+?)\]", re.IGNORECASE)
_VOLUME_RE = re.compile(r"\[VOLUME:\s*(\d+)\]", re.IGNORECASE)
_CMD_RE = re.compile(r"\[CMD:\s*(.+?)\]", re.IGNORECASE)


class Brain:
    def __init__(self, config: dict, memory: ConversationMemory):
        ollama_cfg = config.get("ollama", {})
        self.model: str = ollama_cfg.get("model", "llama3")
        self.host: str = ollama_cfg.get("host", "http://localhost:11434")
        self.context_turns: int = ollama_cfg.get("context_turns", 10)
        self._memory = memory
        self._client = ollama.Client(host=self.host)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process(self, user_text: str) -> str:
        """
        Pass *user_text* to the LLM, handle any tool calls, and return
        the final plain-text response that Jarvis should speak.
        """
        messages = self._build_messages(user_text)
        raw_response = self._chat(messages)
        return self._dispatch(raw_response, user_text)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_messages(self, user_text: str) -> list[dict]:
        history = self._memory.get_recent(self.context_turns)
        messages = [{"role": "system", "content": _SYSTEM_PROMPT}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_text})
        return messages

    def _chat(self, messages: list[dict]) -> str:
        response = self._client.chat(model=self.model, messages=messages)
        return response["message"]["content"].strip()

    def _dispatch(self, raw: str, original_query: str) -> str:
        """Execute any tool tag embedded in the LLM response."""
        if m := _SEARCH_RE.search(raw):
            query = m.group(1).strip()
            context = web_search.search(query)
            # Ask the LLM to summarise the search result in Jarvis voice
            summary_msgs = [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"The user asked: {original_query}\n"
                        f"Web search results: {context}\n"
                        "Summarise the answer in 2-3 sentences."
                    ),
                },
            ]
            return self._chat(summary_msgs)

        if m := _OPEN_RE.search(raw):
            return system_control.open_app(m.group(1).strip())

        if m := _URL_RE.search(raw):
            return system_control.open_url(m.group(1).strip())

        if m := _VOLUME_RE.search(raw):
            return system_control.set_volume(int(m.group(1)))

        if m := _CMD_RE.search(raw):
            return system_control.run_command(m.group(1).strip())

        return raw
