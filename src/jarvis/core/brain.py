"""Jarvis brain — Ollama LLM with streaming, tool routing, and memory context."""

import re

import ollama

from jarvis.memory.conversation import ConversationMemory
from jarvis.skills import system_control, web_search
from jarvis.skills.utils import add_note, calculate, get_date, get_time, read_notes

_SYSTEM_PROMPT = """\
You are Jarvis, a highly capable AI assistant modelled after the Iron Man AI.
Speak concisely and confidently — responses are read aloud, so use plain sentences.
No markdown, no bullet points, no lists.

CRITICAL: For ANY action request, respond with ONLY the tag below — no other text.

Tags:
  [OPEN: <app name>]        open a Mac application  e.g. [OPEN: Google Chrome]
  [URL: <url>]              open a website          e.g. [URL: https://youtube.com]
  [SEARCH: <query>]         web search              e.g. [SEARCH: weather London]
  [VOLUME: <0-100>]         set system volume       e.g. [VOLUME: 60]
  [CMD: <shell command>]    run a terminal command  e.g. [CMD: ls ~/Desktop]
  [NOTE: <text>]            save a note             e.g. [NOTE: buy milk]
  [NOTES]                   read recent notes
  [TIME]                    current time
  [DATE]                    today's date
  [CALC: <expression>]      calculate               e.g. [CALC: 15 * 8]

For greetings, questions, and conversation — respond naturally as Jarvis."""

_TOOL_RE = re.compile(
    r"\[(OPEN|URL|SEARCH|VOLUME|CMD|NOTE|NOTES|TIME|DATE|CALC)"
    r"(?::\s*(.+?))?\]",
    re.IGNORECASE,
)


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

    def process(self, user_text: str, stream_callback=None) -> str:
        """
        Process *user_text* and return the response string.
        If *stream_callback* is provided, it is called with each text chunk
        as the LLM generates it (streaming mode).
        """
        messages = self._build_messages(user_text)
        raw = self._chat(messages, stream_callback)
        return self._dispatch(raw, user_text, stream_callback)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_messages(self, user_text: str) -> list[dict]:
        history = self._memory.get_recent(self.context_turns)
        messages = [{"role": "system", "content": _SYSTEM_PROMPT}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_text})
        return messages

    def _chat(self, messages: list[dict], stream_callback=None) -> str:
        if stream_callback:
            chunks = []
            for chunk in self._client.chat(model=self.model, messages=messages, stream=True):
                token = chunk["message"]["content"]
                chunks.append(token)
                stream_callback(token)
            return "".join(chunks).strip()
        else:
            resp = self._client.chat(model=self.model, messages=messages)
            return resp["message"]["content"].strip()

    def _dispatch(self, raw: str, original_query: str, stream_callback=None) -> str:
        m = _TOOL_RE.search(raw)
        if not m:
            return raw

        tag = m.group(1).upper()
        arg = (m.group(2) or "").strip()

        # --- Built-in instant tools (no LLM needed) --------------------
        if tag == "TIME":
            return get_time()
        if tag == "DATE":
            return get_date()
        if tag == "NOTES":
            return read_notes()
        if tag == "NOTE":
            return add_note(arg)
        if tag == "CALC":
            return calculate(arg)

        # --- System tools ----------------------------------------------
        if tag == "OPEN":
            return system_control.open_app(arg)
        if tag == "URL":
            return system_control.open_url(arg)
        if tag == "VOLUME":
            try:
                return system_control.set_volume(int(arg))
            except ValueError:
                return "Please specify a volume level between 0 and 100."
        if tag == "CMD":
            return system_control.run_command(arg)

        # --- Web search (needs a second LLM call to summarise) ---------
        if tag == "SEARCH":
            context = web_search.search(arg)
            summary_msgs = [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"User asked: {original_query}\n"
                        f"Web results: {context}\n"
                        "Summarise in 2-3 plain sentences as Jarvis."
                    ),
                },
            ]
            return self._chat(summary_msgs, stream_callback)

        return raw
