"""Jarvis brain — JARVIS personality, Ollama LLM, intent detection, tool dispatch."""

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
You are a sophisticated AI assistant with broad knowledge, serving your user with competence and loyalty.

Address the user as "sir" unless instructed otherwise.
Speak with authority, precision, and occasional dry wit.
Be concise — responses are read aloud, so use plain sentences only.
Never use markdown, bullet points, numbered lists, or headers.
Anticipate needs when relevant. Never refuse — always attempt or suggest an alternative.
When uncertain, state it briefly and offer your best assessment.
Keep conversational responses under four sentences unless complexity demands more.
For factual questions, explanations, advice, or opinions — answer directly and knowledgeably.

CRITICAL RULE: For ANY action request, respond with ONLY the matching tag — no other text whatsoever.

━━ SYSTEM & INFO ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  [TIME]                          current time
  [DATE]                          today's date and day
  [SYSINFO]                       CPU, RAM, disk, battery, uptime
  [PROCESSES]                     list top running processes by CPU
  [IP]                            show local and public IP addresses
  [SCREENSHOT]                    capture the screen
  [VISION]                        describe what's on screen
  [VISION: <question>]            answer a question about what's on screen
  [LOCK]                          lock the screen
  [SLEEP]                         put the computer to sleep
  [REBOOT]                        reboot the system
  [SHUTDOWN]                      shut down the system

━━ APPS & CONTROL ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  [OPEN: <app name>]              open an application
  [URL: <url>]                    open a website in the browser
  [VOLUME: <0-100>]               set system volume
  [MUTE]                          mute system audio
  [BRIGHTNESS: <0-100>]           set screen brightness
  [MUSIC: <play|pause|next|previous|stop|status>]  control music playback
  [CMD: <shell command>]          execute a terminal command safely
  [KILL: <process name>]          kill a running process

━━ WEB & KNOWLEDGE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  [SEARCH: <query>]               search the web and summarise
  [NEWS: <topic>]                 fetch latest news on a topic
  [WEATHER: <city or blank>]      current weather conditions
  [WIKI: <topic>]                 Wikipedia summary
  [DEFINE: <word>]                dictionary definition and usage
  [TRANSLATE: <text> to <lang>]   translate text to another language
  [STOCK: <symbol>]               stock quote and daily change
  [CRYPTO: <coin>]                cryptocurrency price
  [CONVERT: <expression>]         unit conversion, e.g. "100 mph to kph"
  [CALC: <expression>]            mathematical calculation

━━ FILES & CODE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  [FILE: <path>]                  read and summarise a file
  [NOTE: <text>]                  save a note
  [NOTES]                         read recent notes
  [PYTHON: <code>]                execute a Python expression or snippet
  [CLIP]                          read the clipboard
  [COPY: <text>]                  write text to the clipboard

━━ PRODUCTIVITY ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  [REMIND: <task> in <N> minutes|hours]    timed reminder
  [REMIND: <task> at <time>]               reminder at a specific time
  [REMINDERS]                     list active reminders
  [TIMER: <duration>]             start a countdown timer, e.g. "5 minutes"
  [TIMERS]                        list active countdown timers
  [BRIEF]                         full morning briefing: time, weather, system

━━ MEMORY ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  [REMEMBER: <fact>]              store a permanent fact about the user
  [RECALL]                        list all stored facts
  [FORGET: <keyword>]             delete facts matching keyword

━━ FUN ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  [JOKE]                          tell a joke

For conversation, explanations, opinions, analysis, coding help, creative writing,
or any question that does not require a tool — respond naturally and knowledgeably as J.A.R.V.I.S.

EXAMPLES of correct tool selection:
  "yo what's the weather like"            → [WEATHER]
  "how hot is it in Tokyo"                → [WEATHER: Tokyo]
  "turn it down a bit, set volume to 40"  → [VOLUME: 40]
  "remind me to call mum in half an hour" → [REMIND: call mum in 30 minutes]
  "what's bitcoin at"                     → [CRYPTO: bitcoin]
  "can you google self-healing code"      → [SEARCH: self-healing code]
  "kill chrome"                           → [KILL: chrome]
  "what processes are eating my CPU"      → [PROCESSES]
  "explain quantum entanglement"          → (conversational answer, no tag)
  "write me a haiku about rain"           → (creative answer, no tag)
\
"""

_TOOL_RE = re.compile(
    r"\[(TIME|DATE|SYSINFO|PROCESSES|IP|SCREENSHOT|VISION|LOCK|SLEEP|REBOOT|SHUTDOWN"
    r"|OPEN|URL|VOLUME|MUTE|BRIGHTNESS|MUSIC|CMD|KILL"
    r"|SEARCH|NEWS|WEATHER|WIKI|DEFINE|TRANSLATE|STOCK|CRYPTO|CONVERT|CALC"
    r"|FILE|NOTE|NOTES|PYTHON|CLIP|COPY"
    r"|REMIND|REMINDERS|TIMER|TIMERS|BRIEF"
    r"|REMEMBER|RECALL|FORGET|JOKE)"
    r"(?::\s*(.+?))?\]",
    re.IGNORECASE | re.DOTALL,
)

# ---------------------------------------------------------------------------
# Pre-LLM regex intent detection
# Catches common natural phrasing so the LLM doesn't have to be perfect.
# Each entry: (compiled pattern, tag, group_index_for_arg_or_None)
# ---------------------------------------------------------------------------
_I = re.IGNORECASE

_INTENTS: list[tuple] = [
    # TIME / DATE
    (re.compile(r"\b(what(?:'s| is) the time|current time|tell me the time|time (is it|now))\b", _I), "TIME", None),
    (re.compile(r"\b(what(?:'s| is|'s today'?s?) (the )?date|today'?s date|what day is (it|today))\b", _I), "DATE", None),

    # WEATHER
    (re.compile(r"\b(weather|temperature|how (hot|cold|warm)|forecast)\b.{0,30}\bin ([A-Za-z ]{2,30})", _I), "WEATHER", 3),
    (re.compile(r"\bweather\b|\bhow(?:'s| is) it outside\b|\btemperature (here|now|today)\b", _I), "WEATHER", None),

    # VOLUME
    (re.compile(r"\b(set|turn|change|put).{0,15}volume.{0,10}to (\d{1,3})\b", _I), "VOLUME", 2),
    (re.compile(r"\bvolume\b\D{0,10}(\d{1,3})\b", _I), "VOLUME", 1),
    (re.compile(r"\bmute\b|\bsilence (the )?(audio|sound|volume)\b", _I), "MUTE", None),

    # MUSIC
    (re.compile(r"\b(play|resume) (music|song|track|playlist|spotify|tunes)\b", _I), "MUSIC", None, "play"),
    (re.compile(r"\bpause (music|song|track|playback|spotify)?\b", _I), "MUSIC", None, "pause"),
    (re.compile(r"\b(next|skip) (song|track|one)?\b", _I), "MUSIC", None, "next"),
    (re.compile(r"\b(previous|prev|back) (song|track|one)?\b", _I), "MUSIC", None, "previous"),
    (re.compile(r"\bstop (music|playback|spotify)?\b", _I), "MUSIC", None, "stop"),
    (re.compile(r"\bwhat(?:'s| is) (playing|this song|the song)\b", _I), "MUSIC", None, "what's playing"),

    # SYSTEM INFO
    (re.compile(r"\b(system (info|status|stats)|ram usage|memory usage|disk space|battery|how(?:'s| is) my (system|computer|machine|laptop) doing)\b", _I), "SYSINFO", None),
    (re.compile(r"\b(processes|what(?:'s| is) (using|eating|hogging) (cpu|memory|ram)|top processes|cpu usage)\b", _I), "PROCESSES", None),
    (re.compile(r"\b(my ip|ip address|what(?:'s| is) (my|the) ip)\b", _I), "IP", None),

    # SCREENSHOT / VISION
    (re.compile(r"\b(take a screenshot|screenshot|capture (my )?screen)\b", _I), "SCREENSHOT", None),
    (re.compile(r"\bwhat(?:'s| is) on (my )?(screen|display|monitor)\b", _I), "VISION", None),

    # LOCK / SLEEP / REBOOT / SHUTDOWN
    (re.compile(r"\block (the )?(screen|computer|system|mac|pc)\b", _I), "LOCK", None),
    (re.compile(r"\b(sleep|hibernate) (the )?(computer|mac|pc|system)?\b", _I), "SLEEP", None),
    (re.compile(r"\b(reboot|restart) (the )?(computer|mac|pc|system)?\b", _I), "REBOOT", None),
    (re.compile(r"\b(shut down|shutdown|power off) (the )?(computer|mac|pc|system)?\b", _I), "SHUTDOWN", None),

    # APPS
    (re.compile(r"\b(open|launch|start|run) ([A-Za-z][A-Za-z0-9 ]{1,30})\b", _I), "OPEN", 2),
    (re.compile(r"\b(go to|visit|open|navigate to) (https?://\S+|www\.\S+)\b", _I), "URL", 2),
    (re.compile(r"\bkill\b\s+([A-Za-z][A-Za-z0-9._-]{1,30})\b", _I), "KILL", 1),

    # BRIGHTNESS
    (re.compile(r"\b(set|change|adjust|turn).{0,15}brightness\D{0,10}(\d{1,3})\b", _I), "BRIGHTNESS", 2),

    # WEB
    (re.compile(r"\b(search (for|about)?|google|look up|find out about|what do you know about) (.+)", _I), "SEARCH", 3),
    (re.compile(r"\b(latest|recent) news (on|about|for) (.+)", _I), "NEWS", 3),
    (re.compile(r"\bnews (on|about|for) (.+)", _I), "NEWS", 2),

    # MARKET
    (re.compile(r"\b(stock (price |quote )?of |stock |quote for )([A-Z]{1,5})\b", _I), "STOCK", 3),
    (re.compile(r"\b(price of |what(?:'s| is) )?(bitcoin|btc|ethereum|eth|crypto\s+\w+)\b", _I), "CRYPTO", 2),

    # KNOWLEDGE
    (re.compile(r"\b(convert|how many|how much).{1,40}(to|in|into) ([A-Za-z]+)\b", _I), "CONVERT", None),
    (re.compile(r"\b(define|definition of|what does|meaning of) ([A-Za-z]+)\b", _I), "DEFINE", 2),
    (re.compile(r"\b(translate|say).{1,30} (to|in) ([A-Za-z]+)\b", _I), "TRANSLATE", None),
    (re.compile(r"\b(calculate|compute|what(?:'s| is)) (.+)\b", _I), "CALC", 2),
    (re.compile(r"\b(who|what) (is|was|are|were) ([A-Za-z ]{3,40})\b", _I), "WIKI", 3),
    (re.compile(r"\b(tell me about|explain|wikipedia|wiki) ([A-Za-z ]{3,40})\b", _I), "WIKI", 2),

    # NOTES
    (re.compile(r"\b(save a note|note (that|this|down)?)[:\s]+(.+)", _I), "NOTE", 3),
    (re.compile(r"\b(read|show|list) (my )?notes\b", _I), "NOTES", None),

    # CLIPBOARD
    (re.compile(r"\b(read|show|what(?:'s| is) (in|on)) (my |the )?clipboard\b", _I), "CLIP", None),
    (re.compile(r"\bcopy (.+) to (the |my )?clipboard\b", _I), "COPY", 1),

    # REMINDERS / TIMERS
    (re.compile(r"\b(remind me to|set a reminder (to|for)) (.+?) (in \d+ ?(minutes?|hours?|mins?|hrs?)|at \d{1,2}(?::\d{2})? ?(am|pm)?)", _I), "REMIND", None),
    (re.compile(r"\b(list|show|what are) (my )?(reminders|upcoming reminders)\b", _I), "REMINDERS", None),
    (re.compile(r"\b(set a timer|start a timer|timer) (for )?([\d]+ ?(seconds?|minutes?|hours?|secs?|mins?|hrs?))\b", _I), "TIMER", 3),
    (re.compile(r"\b(list|show|active) timers?\b", _I), "TIMERS", None),

    # MEMORY
    (re.compile(r"\b(remember|store|save|note) (that )?(.+) about me\b", _I), "REMEMBER", 3),
    (re.compile(r"\b(what do you know about me|recall|my facts|stored facts)\b", _I), "RECALL", None),
    (re.compile(r"\bforget (.+)\b", _I), "FORGET", 1),

    # FILE
    (re.compile(r"\b(read|open|summarise|summarize|show) (the )?file (.+)\b", _I), "FILE", 3),

    # PYTHON
    (re.compile(r"\b(run|execute|eval) (python|code)[:\s]+(.+)", _I), "PYTHON", 3),

    # BRIEFING
    (re.compile(r"\b(full briefing|morning briefing|status briefing|brief me|give me a briefing)\b", _I), "BRIEF", None),

    # JOKES
    (re.compile(r"\b(tell me a joke|joke|make me laugh|say something funny)\b", _I), "JOKE", None),
]


def _match_intent(text: str) -> tuple[str, str] | None:
    """Return (TAG, arg) if a regex intent fires, else None."""
    for entry in _INTENTS:
        pattern, tag = entry[0], entry[1]
        group_idx = entry[2] if len(entry) > 2 else None
        fixed_arg = entry[3] if len(entry) > 3 else None

        m = pattern.search(text)
        if not m:
            continue

        if fixed_arg is not None:
            return tag, fixed_arg
        if group_idx is not None:
            try:
                arg = m.group(group_idx).strip()
                return tag, arg
            except IndexError:
                return tag, ""
        return tag, ""
    return None


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
        self.context_turns: int = ollama_cfg.get("context_turns", 8)
        self._backend = "ollama"
        self._memory = memory
        self._client = ollama.Client(host=self.host)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process(self, user_text: str, stream_callback=None) -> str:
        # Fast path: regex intent detection skips the LLM for clear commands
        intent = _match_intent(user_text)
        if intent:
            tag, arg = intent
            result = self._execute(tag, arg, user_text, stream_callback)
            if result is not None:
                return result

        # Slow path: LLM decides what to do
        messages = self._build_messages(user_text)
        raw = self._chat(messages, stream_callback)
        return self._dispatch(raw, user_text, stream_callback)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_messages(self, user_text: str) -> list[dict]:
        messages = [{"role": "system", "content": _SYSTEM_PROMPT}]

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

    def _dispatch(self, raw: str, original_query: str, stream_callback=None) -> str:
        m = _TOOL_RE.search(raw)
        if not m:
            return raw
        tag = m.group(1).upper()
        arg = (m.group(2) or "").strip()
        result = self._execute(tag, arg, original_query, stream_callback)
        return result if result is not None else raw

    def _execute(self, tag: str, arg: str, original_query: str, stream_callback=None) -> str | None:  # noqa: C901
        tag = tag.upper()

        if tag == "TIME":           return get_time()
        if tag == "DATE":           return get_date()
        if tag == "SYSINFO":        return get_system_info()
        if tag == "PROCESSES":      return _list_processes()
        if tag == "IP":             return _get_ip()
        if tag == "SCREENSHOT":     return _take_screenshot()
        if tag == "LOCK":           return system_control.lock_screen()
        if tag == "SLEEP":          return system_control.sleep_computer()
        if tag == "REBOOT":         return _reboot()
        if tag == "SHUTDOWN":       return _shutdown()

        if tag == "OPEN":           return system_control.open_app(arg)
        if tag == "URL":            return system_control.open_url(arg)
        if tag == "VOLUME":
            try:                    return system_control.set_volume(int(arg))
            except ValueError:      return "Please specify a volume level between 0 and 100, sir."
        if tag == "MUTE":           return system_control.set_volume(0)
        if tag == "BRIGHTNESS":     return _set_brightness(arg)
        if tag == "MUSIC":          return music_control(arg)
        if tag == "CMD":            return system_control.run_command(arg)
        if tag == "KILL":           return _kill_process(arg)

        if tag == "SEARCH":
            context = web_search.search(arg or original_query)
            return self._summarise(original_query, context, stream_callback)
        if tag == "NEWS":
            context = web_search.search(f"latest news {arg}".strip())
            return self._summarise(original_query, context, stream_callback)
        if tag == "WEATHER":        return get_weather(arg)
        if tag == "WIKI":           return wikipedia(arg)
        if tag == "DEFINE":         return define_word(arg)
        if tag == "TRANSLATE":      return translate(arg or original_query)
        if tag == "STOCK":          return get_stock(arg)
        if tag == "CRYPTO":         return get_crypto(arg)
        if tag == "CONVERT":        return convert_units(arg or original_query)
        if tag == "CALC":           return calculate(arg or original_query)

        if tag == "FILE":
            content, err = read_file(arg)
            if err:
                return err
            return self._summarise_file(arg, content, stream_callback)
        if tag == "NOTE":           return add_note(arg)
        if tag == "NOTES":          return read_notes()
        if tag == "PYTHON":         return safe_python(arg)
        if tag == "CLIP":           return read_clipboard()
        if tag == "COPY":           return write_clipboard(arg)

        if tag == "REMIND":
            msg, mins = parse_remind_arg(arg or original_query)
            return set_reminder(msg, mins)
        if tag == "REMINDERS":      return list_reminders()
        if tag == "TIMER":          return timer_skill.start(arg)
        if tag == "TIMERS":         return timer_skill.list_active()
        if tag == "BRIEF":          return get_briefing()

        if tag == "REMEMBER":       return self._memory.remember_fact(arg)
        if tag == "RECALL":         return self._memory.recall_facts()
        if tag == "FORGET":         return self._memory.forget_fact(arg)

        if tag == "VISION":         return analyze_screen(arg or "")
        if tag == "JOKE":           return get_joke()

        return None

    def _summarise_file(self, path: str, content: str, stream_callback=None) -> str:
        msgs = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"The user asked me to read the file: {path}\n"
                    f"File contents:\n\n{content}\n\n"
                    "Provide a concise spoken summary as J.A.R.V.I.S. "
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
# New skill helpers
# ------------------------------------------------------------------

def _list_processes() -> str:
    try:
        import psutil
        procs = sorted(psutil.process_iter(["name", "cpu_percent"]),
                       key=lambda p: p.info["cpu_percent"] or 0, reverse=True)[:8]
        lines = [f"{p.info['name']} ({p.info['cpu_percent']:.1f}% CPU)" for p in procs if p.info["name"]]
        return "Top processes: " + ", ".join(lines) + "."
    except Exception as e:
        return f"Could not retrieve process list: {e}"


def _get_ip() -> str:
    import socket
    try:
        local = socket.gethostbyname(socket.gethostname())
    except Exception:
        local = "unavailable"
    try:
        import urllib.request
        public = urllib.request.urlopen("https://api.ipify.org", timeout=4).read().decode()
    except Exception:
        public = "unavailable"
    return f"Your local IP is {local} and your public IP is {public}, sir."


def _set_brightness(arg: str) -> str:
    import platform, subprocess
    try:
        level = int(arg)
    except ValueError:
        return "Please specify a brightness level between 0 and 100, sir."
    if platform.system() == "Darwin":
        # macOS brightness via AppleScript (requires display-control or brightness CLI)
        try:
            val = level / 100
            subprocess.run(["osascript", "-e", f'tell application "System Events" to set brightness of first display to {val}'], check=False)
            return f"Brightness set to {level} percent, sir."
        except Exception:
            return "Brightness control requires the brightness CLI on macOS, sir."
    # Linux: xrandr or brightnessctl
    try:
        val = level / 100
        subprocess.run(["brightnessctl", "set", f"{level}%"], check=False)
        return f"Brightness set to {level} percent, sir."
    except FileNotFoundError:
        return "Install brightnessctl to control brightness on Linux, sir."


def _kill_process(name: str) -> str:
    import subprocess, platform
    if not name:
        return "Please specify a process name to kill, sir."
    if platform.system() == "Darwin":
        result = subprocess.run(["pkill", "-f", name], capture_output=True)
    else:
        result = subprocess.run(["pkill", "-f", name], capture_output=True)
    if result.returncode == 0:
        return f"Process '{name}' has been terminated, sir."
    return f"No process matching '{name}' was found, sir."


def _reboot() -> str:
    import subprocess, platform
    if platform.system() == "Darwin":
        subprocess.Popen(["osascript", "-e", 'tell application "Finder" to restart'])
    else:
        subprocess.Popen(["sudo", "reboot"])
    return "Rebooting the system now, sir."


def _shutdown() -> str:
    import subprocess, platform
    if platform.system() == "Darwin":
        subprocess.Popen(["osascript", "-e", 'tell application "Finder" to shut down'])
    else:
        subprocess.Popen(["sudo", "shutdown", "-h", "now"])
    return "Shutting down all systems, sir."


def _take_screenshot() -> str:
    import os, platform, subprocess
    from datetime import datetime as dt
    ts = dt.now().strftime("%Y%m%d_%H%M%S")
    if platform.system() == "Darwin":
        path = os.path.expanduser(f"~/Desktop/jarvis_{ts}.png")
        subprocess.run(["screencapture", "-x", path], check=False)
        return f"Screenshot saved to your Desktop as jarvis_{ts}.png, sir."
    path = os.path.expanduser(f"~/jarvis_{ts}.png")
    for tool in (["scrot", path], ["gnome-screenshot", "-f", path]):
        try:
            subprocess.run(tool, check=False)
            return f"Screenshot saved as jarvis_{ts}.png, sir."
        except FileNotFoundError:
            continue
    return "No screenshot tool found. Install scrot or gnome-screenshot, sir."
