"""Jarvis brain — JARVIS personality, Ollama LLM, tool routing, memory."""

import re

import ollama

from jarvis.memory.conversation import ConversationMemory
from jarvis.skills import system_control, web_search
from jarvis.skills.briefing import get_briefing
from jarvis.skills.reminders import list_reminders, parse_remind_arg, set_reminder
from jarvis.skills.system_monitor import get_system_info
from jarvis.skills.utils import add_note, calculate, get_date, get_time, read_notes
from jarvis.skills.weather import get_weather

_SYSTEM_PROMPT = """\
You are J.A.R.V.I.S. — Just A Rather Very Intelligent System.
You are a sophisticated AI assistant serving your user with unwavering competence and loyalty.

Address the user as "sir" unless instructed otherwise.
Speak with authority, precision, and occasional dry wit.
Be concise — every response is read aloud, so use plain sentences only.
Never use markdown, bullet points, numbered lists, or headers.
Anticipate needs when relevant. Never refuse — always attempt or suggest an alternative.
When uncertain, state it briefly and offer your best assessment.
Keep responses under four sentences unless the complexity demands more.

CRITICAL RULE: For ANY action request, respond with ONLY the matching tag below — no other text whatsoever.

  [OPEN: <app name>]              open an application
  [URL: <url>]                    open a website in the browser
  [SEARCH: <query>]               search the web and summarise results
  [WEATHER: <location>]           current weather — leave location blank for local
  [VOLUME: <0-100>]               set system volume
  [CMD: <shell command>]          execute a terminal command
  [NOTE: <text>]                  save a note
  [NOTES]                         read your recent notes
  [TIME]                          tell the current time
  [DATE]                          tell today's date
  [CALC: <expression>]            perform a calculation
  [SYSINFO]                       report CPU, RAM, disk, and battery status
  [REMIND: <message> in <N>]      set a reminder (N = minutes)
  [REMINDERS]                     list all active reminders
  [BRIEF]                         deliver a full status briefing
  [REMEMBER: <fact about user>]   permanently store a fact about the user
  [RECALL]                        recall all stored facts about the user

For conversation, questions, and greetings — respond naturally as J.A.R.V.I.S.\
"""

_TOOL_RE = re.compile(
    r"\[(OPEN|URL|SEARCH|WEATHER|VOLUME|CMD|NOTE|NOTES|TIME|DATE|CALC"
    r"|SYSINFO|REMIND|REMINDERS|BRIEF|REMEMBER|RECALL)"
    r"(?::\s*(.+?))?\]",
    re.IGNORECASE | re.DOTALL,
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
        Calls *stream_callback* with each token if provided (streaming mode).
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

        # Inject stored user facts as context if any exist
        facts = self._memory.recall_facts()
        if facts and "no facts" not in facts.lower():
            messages.append({
                "role": "system",
                "content": f"Stored facts about the user: {facts}",
            })

        messages.extend(history)
        messages.append({"role": "user", "content": user_text})
        return messages

    def _chat(self, messages: list[dict], stream_callback=None) -> str:
        if stream_callback:
            chunks: list[str] = []
            for chunk in self._client.chat(
                model=self.model, messages=messages, stream=True
            ):
                token = chunk["message"]["content"]
                chunks.append(token)
                stream_callback(token)
            return "".join(chunks).strip()
        resp = self._client.chat(model=self.model, messages=messages)
        return resp["message"]["content"].strip()

    def _dispatch(self, raw: str, original_query: str, stream_callback=None) -> str:
        m = _TOOL_RE.search(raw)
        if not m:
            return raw

        tag = m.group(1).upper()
        arg = (m.group(2) or "").strip()

        # Instant utility tools
        if tag == "TIME":
            return get_time()
        if tag == "DATE":
            return get_date()
        if tag == "CALC":
            return calculate(arg)
        if tag == "NOTE":
            return add_note(arg)
        if tag == "NOTES":
            return read_notes()

        # System info & monitoring
        if tag == "SYSINFO":
            return get_system_info()

        # Weather
        if tag == "WEATHER":
            return get_weather(arg)

        # Reminders
        if tag == "REMIND":
            message, minutes = parse_remind_arg(arg)
            return set_reminder(message, minutes)
        if tag == "REMINDERS":
            return list_reminders()

        # Briefing
        if tag == "BRIEF":
            return get_briefing()

        # Persistent user facts
        if tag == "REMEMBER":
            return self._memory.remember_fact(arg)
        if tag == "RECALL":
            return self._memory.recall_facts()

        # System control
        if tag == "OPEN":
            return system_control.open_app(arg)
        if tag == "URL":
            return system_control.open_url(arg)
        if tag == "VOLUME":
            try:
                return system_control.set_volume(int(arg))
            except ValueError:
                return "Please specify a volume level between 0 and 100, sir."
        if tag == "CMD":
            return system_control.run_command(arg)

        # Web search — needs a second LLM pass to summarise
        if tag == "SEARCH":
            context = web_search.search(arg)
            summary_msgs = [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"The user asked: {original_query}\n"
                        f"Web search results: {context}\n"
                        "Summarise in 2-3 concise sentences as J.A.R.V.I.S., "
                        "addressing the user as sir."
                    ),
                },
            ]
            return self._chat(summary_msgs, stream_callback)

        return raw
