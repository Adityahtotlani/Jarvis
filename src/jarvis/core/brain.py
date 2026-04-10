"""Jarvis brain — JARVIS personality, Ollama LLM, tool routing, memory."""

import re
from datetime import datetime

import ollama

from jarvis.memory.conversation import ConversationMemory
from jarvis.skills import system_control, web_search
from jarvis.skills import timer as timer_skill
from jarvis.skills.briefing import get_briefing
from jarvis.skills.clipboard import read_clipboard, write_clipboard
from jarvis.skills.convert import convert as convert_units
from jarvis.skills.dictionary import define as define_word
from jarvis.skills.files import read_file, safe_python
from jarvis.skills.jokes import get_joke
from jarvis.skills.lookup import translate, wikipedia
from jarvis.skills.market import get_crypto, get_stock
from jarvis.skills.music import control as music_control
from jarvis.skills.reminders import list_reminders, parse_remind_arg, set_reminder
from jarvis.skills.system_monitor import get_system_info
from jarvis.skills.utils import add_note, calculate, get_date, get_time, read_notes
from jarvis.skills.vision import analyze_screen
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

CRITICAL RULE: For ANY action request, respond with ONLY the matching tag — no other text.

  [OPEN: <app name>]              open an application
  [URL: <url>]                    open a website in the browser
  [SEARCH: <query>]               search the web and summarise results
  [NEWS: <topic>]                 fetch the latest news on a topic
  [WEATHER: <location>]           current weather — blank for local
  [VOLUME: <0-100>]               set system volume
  [MUSIC: <command>]              control music (play/pause/next/previous/stop/what's playing)
  [CMD: <shell command>]          execute a terminal command
  [NOTE: <text>]                  save a note
  [NOTES]                         read recent notes
  [TIME]                          tell the current time
  [DATE]                          tell today's date
  [CALC: <expression>]            perform a calculation
  [SYSINFO]                       report CPU, RAM, disk, and battery status
  [REMIND: <message> in <N>]      set a reminder (N = minutes)
  [REMINDERS]                     list all active reminders
  [BRIEF]                         deliver a full status briefing
  [REMEMBER: <fact about user>]   permanently store a fact about the user
  [RECALL]                        recall all stored facts about the user
  [FORGET: <keyword>]             delete stored facts matching keyword
  [CLIP]                          read the clipboard
  [COPY: <text>]                  write text to the clipboard
  [SCREENSHOT]                    take a screenshot
  [WIKI: <topic>]                 Wikipedia summary on any topic
  [TRANSLATE: <text> to <lang>]   translate text to another language
  [FILE: <path>]                  read and summarise a file
  [PYTHON: <code>]                execute a Python expression or snippet
  [VISION]                        describe what's currently on screen
  [VISION: <question>]            answer a question about what's on screen
  [STOCK: <symbol>]               fetch a stock quote
  [CRYPTO: <coin>]                fetch a crypto price
  [CONVERT: <expression>]         convert units, e.g. '5 miles to km'
  [DEFINE: <word>]                look up a word's definition
  [TIMER: <duration>]             start a countdown timer
  [TIMERS]                        list active countdown timers
  [JOKE]                          tell a joke
  [LOCK]                          lock the screen
  [SLEEP]                         put the computer to sleep

For conversation, questions, and greetings — respond naturally as J.A.R.V.I.S.\
"""

_TOOL_RE = re.compile(
    r"\[(OPEN|URL|SEARCH|NEWS|WEATHER|VOLUME|MUSIC|CMD|NOTE|NOTES|TIME|DATE|CALC"
    r"|SYSINFO|REMIND|REMINDERS|BRIEF|REMEMBER|RECALL|FORGET|CLIP|COPY|SCREENSHOT"
    r"|WIKI|TRANSLATE|FILE|PYTHON"
    r"|VISION|STOCK|CRYPTO|CONVERT|DEFINE|TIMER|TIMERS|JOKE|LOCK|SLEEP)"
    r"(?::\s*(.+?))?\]",
    re.IGNORECASE | re.DOTALL,
)


def _time_of_day() -> str:
    h = datetime.now().hour
    if 5 <= h < 12:
        return "morning"
    if 12 <= h < 17:
        return "afternoon"
    return "evening"


class Brain:
    def __init__(self, config: dict, memory: ConversationMemory):
        ollama_cfg = config.get("ollama", {})
        self.model: str = ollama_cfg.get("model", "llama3.2:1b")
        self.host: str = ollama_cfg.get("host", "http://localhost:11434")
        self.context_turns: int = ollama_cfg.get("context_turns", 6)
        self._memory = memory
        self._client = ollama.Client(host=self.host)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process(self, user_text: str, stream_callback=None) -> str:
        """
        Process *user_text* and return the response string.
        Calls *stream_callback* with each token if streaming is desired.
        """
        messages = self._build_messages(user_text)
        raw = self._chat(messages, stream_callback)
        return self._dispatch(raw, user_text, stream_callback)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_messages(self, user_text: str) -> list[dict]:
        messages = [{"role": "system", "content": _SYSTEM_PROMPT}]

        # Inject time-of-day and stored facts as system context
        context_parts = [f"Current time of day: {_time_of_day()}."]
        facts = self._memory.recall_facts()
        if "no stored" not in facts.lower():
            context_parts.append(f"Stored facts about the user: {facts}")
        messages.append({"role": "system", "content": " ".join(context_parts)})

        messages.extend(self._memory.get_recent(self.context_turns))
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

    def _dispatch(self, raw: str, original_query: str, stream_callback=None) -> str:  # noqa: C901
        m = _TOOL_RE.search(raw)
        if not m:
            return raw

        tag = m.group(1).upper()
        arg = (m.group(2) or "").strip()

        # Instant utilities
        if tag == "TIME":           return get_time()
        if tag == "DATE":           return get_date()
        if tag == "CALC":           return calculate(arg)
        if tag == "NOTE":           return add_note(arg)
        if tag == "NOTES":          return read_notes()

        # System
        if tag == "SYSINFO":        return get_system_info()
        if tag == "SCREENSHOT":     return _take_screenshot()

        # Knowledge & code
        if tag == "WIKI":           return wikipedia(arg)
        if tag == "TRANSLATE":      return translate(arg)
        if tag == "PYTHON":         return safe_python(arg)
        if tag == "FILE":
            content, err = read_file(arg)
            if err:
                return err
            return self._summarise_file(arg, content, stream_callback)

        # Weather / news
        if tag == "WEATHER":        return get_weather(arg)
        if tag == "NEWS":
            context = web_search.search(f"latest news {arg}".strip())
            return self._summarise(original_query, context, stream_callback)

        # Music / clipboard
        if tag == "MUSIC":          return music_control(arg)
        if tag == "CLIP":           return read_clipboard()
        if tag == "COPY":           return write_clipboard(arg)

        # Reminders
        if tag == "REMIND":
            msg, mins = parse_remind_arg(arg)
            return set_reminder(msg, mins)
        if tag == "REMINDERS":      return list_reminders()

        # Briefing
        if tag == "BRIEF":          return get_briefing()

        # Memory
        if tag == "REMEMBER":       return self._memory.remember_fact(arg)
        if tag == "RECALL":         return self._memory.recall_facts()
        if tag == "FORGET":         return self._memory.forget_fact(arg)

        # System control
        if tag == "OPEN":           return system_control.open_app(arg)
        if tag == "URL":            return system_control.open_url(arg)
        if tag == "VOLUME":
            try:                    return system_control.set_volume(int(arg))
            except ValueError:      return "Please specify a volume between 0 and 100, sir."
        if tag == "CMD":            return system_control.run_command(arg)

        # Web search
        if tag == "SEARCH":
            context = web_search.search(arg)
            return self._summarise(original_query, context, stream_callback)

        # Vision
        if tag == "VISION":         return analyze_screen(arg or "")

        # Market data
        if tag == "STOCK":          return get_stock(arg)
        if tag == "CRYPTO":         return get_crypto(arg)

        # Knowledge helpers
        if tag == "CONVERT":        return convert_units(arg)
        if tag == "DEFINE":         return define_word(arg)
        if tag == "JOKE":           return get_joke()

        # Timers
        if tag == "TIMER":          return timer_skill.start(arg)
        if tag == "TIMERS":         return timer_skill.list_active()

        # Power
        if tag == "LOCK":           return system_control.lock_screen()
        if tag == "SLEEP":          return system_control.sleep_computer()

        return raw

    def _summarise_file(self, path: str, content: str, stream_callback=None) -> str:
        msgs = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"The user asked me to read the file: {path}\n"
                    f"File contents:\n\n{content}\n\n"
                    "Provide a concise spoken summary of this file as J.A.R.V.I.S. "
                    "Mention the file type, purpose, and key contents. "
                    "Address the user as sir. Keep it under five sentences."
                ),
            },
        ]
        return self._chat(msgs, stream_callback)

    def _summarise(self, query: str, context: str, stream_callback=None) -> str:
        msgs = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"User asked: {query}\n"
                    f"Results: {context}\n"
                    "Summarise in 2-3 sentences as J.A.R.V.I.S., addressing the user as sir."
                ),
            },
        ]
        return self._chat(msgs, stream_callback)


# ------------------------------------------------------------------
# Screenshot helper (outside class to keep it simple)
# ------------------------------------------------------------------

def _take_screenshot() -> str:
    import os
    import platform
    import subprocess
    from datetime import datetime

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    if platform.system() == "Darwin":
        path = os.path.expanduser(f"~/Desktop/jarvis_{ts}.png")
        subprocess.run(["screencapture", "-x", path], check=False)
        return f"Screenshot saved to your Desktop as jarvis_{ts}.png, sir."
    # Linux
    path = os.path.expanduser(f"~/jarvis_{ts}.png")
    try:
        subprocess.run(["scrot", path], check=False)
        return f"Screenshot saved as jarvis_{ts}.png, sir."
    except FileNotFoundError:
        try:
            subprocess.run(["gnome-screenshot", "-f", path], check=False)
            return f"Screenshot saved as jarvis_{ts}.png, sir."
        except FileNotFoundError:
            return "Screenshot tool not found. Install scrot or gnome-screenshot, sir."
