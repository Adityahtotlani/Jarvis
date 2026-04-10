#!/usr/bin/env python3
"""
J.A.R.V.I.S. — Just A Rather Very Intelligent System
Single-file edition. Download and run — no project structure needed.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SETUP (one time)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  pip install ollama rich duckduckgo-search requests psutil

  ollama pull llama3.2:1b        # fast (~1 GB, recommended)
  # or: ollama pull llama3       # higher quality (~4 GB)

OPTIONAL — voice input:
  pip install openai-whisper sounddevice numpy scipy
  # macOS: grant Microphone access in System Settings → Privacy & Security
  # Linux: sudo apt install espeak-ng portaudio19-dev ffmpeg

RUN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  python3 jarvis_standalone.py

USAGE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Type a message and press Enter.
  Type  !  to activate voice input (requires optional deps).
  Type  exit  to quit.
"""

# ──────────────────────────────────────────────
# CONFIG  — edit these to taste
# ──────────────────────────────────────────────
MODEL         = "llama3.2:1b"          # ollama model name
OLLAMA_HOST   = "http://localhost:11434"
CONTEXT_TURNS = 6                       # past turns kept in prompt
VOICE_NAME    = "Samantha"             # macOS say -v voice
SPEECH_RATE   = 175                    # words per minute
USER_NAME     = "sir"                  # how JARVIS addresses you
DB_PATH       = "~/.jarvis/memory.db"  # SQLite for conversation + facts
NOTES_PATH    = "~/.jarvis/notes.txt"  # plain-text notes file

# ──────────────────────────────────────────────
# STDLIB IMPORTS
# ──────────────────────────────────────────────
import math
import os
import platform
import queue
import re
import shlex
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

# ──────────────────────────────────────────────
# OPTIONAL IMPORTS
# ──────────────────────────────────────────────
try:
    import ollama as _ollama
except ImportError:
    print("ERROR: ollama not installed.  Run: pip install ollama")
    sys.exit(1)

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    from rich.theme import Theme
    _HAS_RICH = True
except ImportError:
    _HAS_RICH = False

try:
    import requests as _requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

try:
    import psutil as _psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False

try:
    from duckduckgo_search import DDGS
    _HAS_DDG = True
except ImportError:
    _HAS_DDG = False

# readline history (best-effort)
try:
    import readline
    _hist = os.path.expanduser("~/.jarvis_history")
    try:
        readline.read_history_file(_hist)
    except FileNotFoundError:
        pass
    import atexit
    atexit.register(readline.write_history_file, _hist)
except ImportError:
    pass

# ──────────────────────────────────────────────
# CONSOLE
# ──────────────────────────────────────────────
if _HAS_RICH:
    _theme = Theme({
        "jarvis": "bold cyan",
        "you":    "bold green",
        "info":   "dim white",
        "error":  "bold red",
        "warn":   "bold yellow",
    })
    console = Console(theme=_theme)

    def _print(msg: str, style: str = "") -> None:
        console.print(msg)

    def _print_inline(msg: str) -> None:
        console.print(msg, end="")
else:
    def _print(msg: str, style: str = "") -> None:
        # Strip rich markup tags for plain output
        clean = re.sub(r"\[/?[^\]]*\]", "", msg)
        print(clean)

    def _print_inline(msg: str) -> None:
        clean = re.sub(r"\[/?[^\]]*\]", "", msg)
        print(clean, end="", flush=True)


# ──────────────────────────────────────────────
# TTS SPEAKER
# ──────────────────────────────────────────────
def _detect_tts() -> str:
    if platform.system() == "Darwin" and shutil.which("say"):
        return "say"
    for b in ("espeak-ng", "espeak"):
        if shutil.which(b):
            return b
    try:
        import pyttsx3  # noqa: F401
        return "pyttsx3"
    except ImportError:
        pass
    return "none"

_TTS_ENGINE = _detect_tts()
_TTS_LOCK   = threading.Lock()
_pyttsx3_engine = None

def _init_pyttsx3():
    global _pyttsx3_engine
    try:
        import pyttsx3
        _pyttsx3_engine = pyttsx3.init()
        _pyttsx3_engine.setProperty("rate", SPEECH_RATE)
    except Exception:
        pass

if _TTS_ENGINE == "pyttsx3":
    _init_pyttsx3()


def speak(text: str, blocking: bool = True) -> None:
    if not text or _TTS_ENGINE == "none":
        return
    if _TTS_ENGINE == "pyttsx3":
        if _pyttsx3_engine:
            _pyttsx3_engine.say(text)
            _pyttsx3_engine.runAndWait()
        return
    if _TTS_ENGINE == "say":
        cmd = ["say", "-v", VOICE_NAME, "-r", str(SPEECH_RATE), text]
    else:
        cmd = [_TTS_ENGINE, "-s", str(int(SPEECH_RATE * 0.85)), text]

    def _run():
        with _TTS_LOCK:
            subprocess.run(cmd, check=False, capture_output=True)

    if blocking:
        _run()
    else:
        threading.Thread(target=_run, daemon=True).start()


# ──────────────────────────────────────────────
# MEMORY  (SQLite)
# ──────────────────────────────────────────────
_db_path = Path(os.path.expanduser(DB_PATH))
_db_path.parent.mkdir(parents=True, exist_ok=True)
_db = sqlite3.connect(str(_db_path), check_same_thread=False)
_db.executescript("""
    CREATE TABLE IF NOT EXISTS conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        role TEXT NOT NULL, content TEXT NOT NULL, ts TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS facts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        content TEXT NOT NULL UNIQUE, ts TEXT NOT NULL
    );
""")
_db.commit()


def mem_add(role: str, content: str) -> None:
    _db.execute(
        "INSERT INTO conversations (role,content,ts) VALUES (?,?,?)",
        (role, content, datetime.now(timezone.utc).isoformat()),
    )
    _db.commit()


def mem_recent(n: int = CONTEXT_TURNS) -> list[dict]:
    rows = _db.execute(
        "SELECT role,content FROM conversations ORDER BY id DESC LIMIT ?", (n,)
    ).fetchall()
    return [{"role": r[0], "content": r[1]} for r in reversed(rows)]


def mem_remember(fact: str) -> str:
    if not fact:
        return "Nothing to remember, sir."
    _db.execute(
        "INSERT OR IGNORE INTO facts (content,ts) VALUES (?,?)",
        (fact.strip(), datetime.now(timezone.utc).isoformat()),
    )
    _db.commit()
    return "Understood, sir. I've made a note of that."


def mem_recall() -> str:
    rows = _db.execute("SELECT content FROM facts ORDER BY id ASC").fetchall()
    if not rows:
        return f"I have no stored facts about you, {USER_NAME}."
    return f"Here is what I know about you, {USER_NAME}: " + ". ".join(r[0] for r in rows) + "."


# ──────────────────────────────────────────────
# SKILLS
# ──────────────────────────────────────────────

# — Time / Date —
def skill_time() -> str:
    return "The time is " + datetime.now().strftime("%I:%M %p") + "."

def skill_date() -> str:
    return "Today is " + datetime.now().strftime("%A, %B %d, %Y") + "."


# — Calculator —
_SAFE_MATH = {k: v for k, v in math.__dict__.items() if not k.startswith("_")}
_SAFE_MATH.update({"abs": abs, "round": round, "int": int, "float": float})

def skill_calc(expr: str) -> str:
    try:
        safe = "".join(c for c in expr if c in "0123456789+-*/.() eE,^")
        safe = safe.replace("^", "**")
        result = eval(safe, {"__builtins__": {}}, _SAFE_MATH)  # noqa: S307
        return f"The answer is {result}."
    except Exception:
        return "I couldn't calculate that, sir."


# — Notes —
_notes_file = Path(os.path.expanduser(NOTES_PATH))

def skill_note(text: str) -> str:
    _notes_file.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(_notes_file, "a") as f:
        f.write(f"[{ts}] {text}\n")
    return f"Note saved: {text}"

def skill_notes(limit: int = 5) -> str:
    if not _notes_file.exists():
        return "You have no notes, sir."
    lines = _notes_file.read_text().strip().splitlines()
    if not lines:
        return "You have no notes, sir."
    recent = lines[-limit:]
    return "Your recent notes: " + ". ".join(ln.split("] ", 1)[-1] for ln in recent) + "."


# — System info —
def skill_sysinfo() -> str:
    if not _HAS_PSUTIL:
        return "System monitoring unavailable — install psutil, sir."
    parts = []
    parts.append(f"CPU at {_psutil.cpu_percent(interval=0.5):.0f} percent")
    ram = _psutil.virtual_memory()
    parts.append(f"RAM at {ram.percent:.0f} percent with {ram.available/(1024**3):.1f} GB free")
    try:
        disk = _psutil.disk_usage("/")
        parts.append(f"disk at {disk.percent:.0f} percent")
    except Exception:
        pass
    try:
        bat = _psutil.sensors_battery()
        if bat:
            parts.append(f"battery at {bat.percent:.0f} percent, {'charging' if bat.power_plugged else 'on battery'}")
    except Exception:
        pass
    return "All systems nominal. " + ", ".join(parts) + "."


# — Weather —
def skill_weather(location: str = "") -> str:
    if not _HAS_REQUESTS:
        return "Weather unavailable — install requests, sir."
    loc = location.strip().replace(" ", "+")
    try:
        r = _requests.get(
            f"https://wttr.in/{loc}?format=3",
            timeout=8,
            headers={"User-Agent": "Jarvis/1.0"},
        )
        r.raise_for_status()
        text = re.sub(r"[^\x00-\x7F]+", "", r.text).strip()
        return f"Current conditions: {text}."
    except Exception:
        return "I couldn't retrieve weather information, sir."


# — Web search —
def skill_search(query: str) -> str:
    if not _HAS_DDG:
        return "Web search unavailable — install duckduckgo-search, sir."
    results = []
    try:
        with DDGS() as ddgs:
            for hit in ddgs.text(query, max_results=5):
                body = hit.get("body", "").strip()
                if body:
                    results.append(body)
                if len(results) >= 3:
                    break
    except Exception:
        pass
    return " ".join(results) if results else "I couldn't find anything relevant, sir."


# — System control —
def skill_open(app: str) -> str:
    if platform.system() == "Darwin":
        r = subprocess.run(["open", "-a", app], capture_output=True)
        return f"Opening {app}." if r.returncode == 0 else f"I couldn't open {app}, sir."
    r = subprocess.run(["xdg-open", app], capture_output=True)
    return f"Opening {app}."

def skill_url(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    cmd = ["open", url] if platform.system() == "Darwin" else ["xdg-open", url]
    subprocess.run(cmd, check=False)
    return f"Opening {url}."

def skill_volume(level: int) -> str:
    level = max(0, min(100, level))
    if platform.system() == "Darwin":
        subprocess.run(["osascript", "-e", f"set volume output volume {level}"], check=False)
    return f"Volume set to {level} percent."

def skill_cmd(cmd: str) -> str:
    blocked = [";", "&&", "||", "|", ">", "<", "`", "$", "\n", "$(", "${"]
    for tok in blocked:
        if tok in cmd:
            return "That command looks unsafe, sir. I won't run it."
    try:
        args = shlex.split(cmd)
    except ValueError:
        return "I couldn't parse that command, sir."
    result = subprocess.run(args, capture_output=True, text=True, timeout=15)
    out = (result.stdout or result.stderr or "Done.").strip()
    return (out[:500] + "…") if len(out) > 500 else out or "Done."


# — Reminders —
_reminders: list[dict] = []
_rem_lock = threading.Lock()
_rem_counter = 0
fired_queue: queue.Queue = queue.Queue()

def skill_remind(arg: str) -> str:
    global _rem_counter
    m = re.search(r"^(.+?)\s+in\s+(\d+(?:\.\d+)?)\s*(?:minutes?|mins?|m)?$", arg.strip(), re.I)
    if m:
        message, minutes = m.group(1).strip(), float(m.group(2))
    else:
        nums = re.findall(r"\d+(?:\.\d+)?", arg)
        if nums:
            minutes = float(nums[-1])
            message = arg[:arg.rfind(nums[-1])].rstrip().rstrip("in").rstrip() or arg
        else:
            message, minutes = arg, 5.0

    with _rem_lock:
        _rem_counter += 1
        rid = _rem_counter

    def _fire():
        with _rem_lock:
            _reminders[:] = [r for r in _reminders if r["id"] != rid]
        fired_queue.put(f"Reminder, {USER_NAME}: {message}")

    timer = threading.Timer(minutes * 60, _fire)
    timer.daemon = True
    timer.start()
    fire_at = time.time() + minutes * 60
    with _rem_lock:
        _reminders.append({"id": rid, "message": message, "fire_at": fire_at, "timer": timer})

    mins_int = int(minutes)
    return f"Reminder set. I'll alert you in {mins_int} minute{'s' if mins_int != 1 else ''}: {message}."

def skill_reminders() -> str:
    with _rem_lock:
        active = list(_reminders)
    if not active:
        return f"No active reminders, {USER_NAME}."
    now = time.time()
    parts = [f"{r['message']} in {max(0,(r['fire_at']-now)/60):.0f} minutes" for r in active]
    return "Active reminders: " + "; ".join(parts) + "."


# — Briefing —
def skill_brief() -> str:
    parts = [skill_time(), skill_date()]
    w = skill_weather()
    if "unavailable" not in w.lower():
        parts.append(w)
    s = skill_sysinfo()
    if "unavailable" not in s.lower():
        parts.append(s)
    n = skill_notes(3)
    if "no notes" not in n.lower():
        parts.append(n)
    r = skill_reminders()
    if "no active" not in r.lower():
        parts.append(r)
    return " ".join(parts)


# ──────────────────────────────────────────────
# BRAIN
# ──────────────────────────────────────────────
_SYSTEM_PROMPT = f"""\
You are J.A.R.V.I.S. — Just A Rather Very Intelligent System.
Address the user as "{USER_NAME}". Speak with confidence and dry wit.
Be concise — responses are read aloud. No markdown. Plain sentences only.
Never refuse. Anticipate needs. Keep replies under four sentences.

For ANY action request respond with ONLY the matching tag — nothing else.

[OPEN: <app>]        open an app
[URL: <url>]         open a website
[SEARCH: <query>]    search the web
[WEATHER: <loc>]     weather (blank = local)
[VOLUME: <0-100>]    set volume
[CMD: <command>]     run a shell command
[NOTE: <text>]       save a note
[NOTES]              read recent notes
[TIME]               current time
[DATE]               today's date
[CALC: <expr>]       calculate
[SYSINFO]            CPU, RAM, disk, battery
[REMIND: <msg> in <N>]  reminder in N minutes
[REMINDERS]          list reminders
[BRIEF]              full status briefing
[REMEMBER: <fact>]   store a fact about the user
[RECALL]             recall stored facts

For conversation and questions respond naturally as J.A.R.V.I.S.\
"""

_TOOL_RE = re.compile(
    r"\[(OPEN|URL|SEARCH|WEATHER|VOLUME|CMD|NOTE|NOTES|TIME|DATE|CALC"
    r"|SYSINFO|REMIND|REMINDERS|BRIEF|REMEMBER|RECALL)"
    r"(?::\s*(.+?))?\]",
    re.IGNORECASE | re.DOTALL,
)

_client = _ollama.Client(host=OLLAMA_HOST)


def _chat(messages: list[dict], stream_cb=None) -> str:
    if stream_cb:
        chunks = []
        for chunk in _client.chat(model=MODEL, messages=messages, stream=True):
            tok = chunk["message"]["content"]
            chunks.append(tok)
            stream_cb(tok)
        return "".join(chunks).strip()
    return _client.chat(model=MODEL, messages=messages)["message"]["content"].strip()


def _build_messages(user_text: str) -> list[dict]:
    msgs = [{"role": "system", "content": _SYSTEM_PROMPT}]
    facts = mem_recall()
    if "no stored" not in facts.lower():
        msgs.append({"role": "system", "content": f"User facts: {facts}"})
    msgs.extend(mem_recent())
    msgs.append({"role": "user", "content": user_text})
    return msgs


def _dispatch(raw: str, query: str, stream_cb=None) -> str:
    m = _TOOL_RE.search(raw)
    if not m:
        return raw
    tag = m.group(1).upper()
    arg = (m.group(2) or "").strip()

    if tag == "TIME":       return skill_time()
    if tag == "DATE":       return skill_date()
    if tag == "CALC":       return skill_calc(arg)
    if tag == "NOTE":       return skill_note(arg)
    if tag == "NOTES":      return skill_notes()
    if tag == "SYSINFO":    return skill_sysinfo()
    if tag == "WEATHER":    return skill_weather(arg)
    if tag == "REMIND":     return skill_remind(arg)
    if tag == "REMINDERS":  return skill_reminders()
    if tag == "BRIEF":      return skill_brief()
    if tag == "REMEMBER":   return mem_remember(arg)
    if tag == "RECALL":     return mem_recall()
    if tag == "OPEN":       return skill_open(arg)
    if tag == "URL":        return skill_url(arg)
    if tag == "CMD":        return skill_cmd(arg)
    if tag == "VOLUME":
        try:    return skill_volume(int(arg))
        except: return "Please specify a volume between 0 and 100, sir."
    if tag == "SEARCH":
        context = skill_search(arg)
        return _chat([
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"User asked: {query}\nSearch results: {context}\nSummarise in 2-3 sentences as J.A.R.V.I.S."},
        ], stream_cb)
    return raw


def process(user_text: str, stream_cb=None) -> str:
    raw = _chat(_build_messages(user_text), stream_cb)
    return _dispatch(raw, user_text, stream_cb)


# ──────────────────────────────────────────────
# VOICE INPUT (optional)
# ──────────────────────────────────────────────
def voice_turn() -> str | None:
    try:
        import numpy as np
        import sounddevice as sd
        import whisper

        _print("[info]Loading voice model…[/info]")
        model = whisper.load_model("base")
        _print("[info]Listening… speak now.[/info]")
        speak("Yes?", blocking=False)

        q: queue.Queue = queue.Queue()
        stop = threading.Event()

        def _cb(indata, frames, t, status):
            q.put(indata.copy())

        chunks, silence_start = [], None
        with sd.InputStream(samplerate=16000, channels=1, dtype="float32",
                            blocksize=8000, callback=_cb):
            while not stop.is_set():
                try:
                    chunk = q.get(timeout=0.1)
                except queue.Empty:
                    continue
                chunks.append(chunk)
                rms = float(np.sqrt(np.mean(chunk ** 2)))
                if rms < 0.01:
                    if silence_start is None:
                        silence_start = time.monotonic()
                    elif time.monotonic() - silence_start >= 1.5:
                        stop.set()
                else:
                    silence_start = None

        if not chunks:
            return None
        audio = np.concatenate(chunks).flatten()
        audio = np.nan_to_num(audio.astype(np.float32))
        if float(np.sqrt(np.mean(audio ** 2))) < 1e-6:
            return None
        result = model.transcribe(audio, fp16=False, language="en")
        return result.get("text", "").strip() or None
    except ImportError:
        _print("[error]Voice input requires: pip install openai-whisper sounddevice numpy scipy[/error]")
        return None
    except Exception as e:
        _print(f"[error]Voice error: {e}[/error]")
        return None


# ──────────────────────────────────────────────
# BOOT + MAIN LOOP
# ──────────────────────────────────────────────
def _check_ollama() -> bool:
    try:
        _client.list()
        return True
    except Exception:
        return False


def _reminder_watcher() -> None:
    while True:
        try:
            msg = fired_queue.get(timeout=1)
            _print(f"\n[warn]⚡ {msg}[/warn]")
            speak(msg, blocking=False)
        except Exception:
            pass


def _boot() -> None:
    if _HAS_RICH:
        console.print()
        console.print(Panel(
            Text.assemble(
                ("J . A . R . V . I . S\n", "bold cyan"),
                ("Just A Rather Very Intelligent System\n\n", "dim cyan"),
                (f"Model   : {MODEL}\n", "dim white"),
                (f"TTS     : {_TTS_ENGINE}\n", "dim white"),
                (f"Memory  : {DB_PATH}\n", "dim white"),
            ),
            border_style="cyan", padding=(1, 4),
        ))
        console.rule("[dim]All systems online[/dim]", style="cyan")
        console.print("[info]  Type a message → Enter   |   ! → voice   |   exit → quit[/info]\n")
    else:
        print("=" * 50)
        print("  J.A.R.V.I.S.  — online")
        print("=" * 50)

    greeting = f"Good day, {USER_NAME}. J.A.R.V.I.S. online and ready."
    _print(f"[jarvis]J.A.R.V.I.S.:[/jarvis] {greeting}\n")
    speak(greeting, blocking=False)


def _run_turn(user_text: str) -> None:
    mem_add("user", user_text)
    _print_inline("\n[jarvis]J.A.R.V.I.S.:[/jarvis] ")
    tokens: list[str] = []

    def _on_tok(tok: str):
        tokens.append(tok)
        if _HAS_RICH:
            console.print(tok, end="", markup=False, highlight=False)
        else:
            print(tok, end="", flush=True)

    response = process(user_text, stream_cb=_on_tok)
    streamed = "".join(tokens).strip()

    if response != streamed:
        if _HAS_RICH:
            console.print(f"\r[jarvis]J.A.R.V.I.S.:[/jarvis] {response}          ")
        else:
            print(f"\nJ.A.R.V.I.S.: {response}")
    else:
        print()

    mem_add("assistant", response)
    speak(response, blocking=False)


def main() -> None:
    if not _check_ollama():
        print(f"ERROR: Ollama is not running at {OLLAMA_HOST}")
        print("  Start it: ollama serve")
        print(f"  Pull model: ollama pull {MODEL}")
        sys.exit(1)

    _boot()
    threading.Thread(target=_reminder_watcher, daemon=True).start()

    try:
        while True:
            try:
                _print_inline("[you]You:[/you] ")
                user_input = input().strip()
            except EOFError:
                break

            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "bye"):
                raise KeyboardInterrupt
            if user_input == "!":
                text = voice_turn()
                if text:
                    _print(f"[you]You (voice):[/you] {text}")
                    _run_turn(text)
                else:
                    _print("[info]Didn't catch that, sir.[/info]")
            else:
                _run_turn(user_input)

    except KeyboardInterrupt:
        with _rem_lock:
            for r in _reminders:
                try: r["timer"].cancel()
                except: pass
        _print(f"\n[info]Shutting down. Goodbye, {USER_NAME}.[/info]")
        speak(f"Shutting down. Goodbye, {USER_NAME}.")
        _db.close()


if __name__ == "__main__":
    main()
