#!/usr/bin/env python3
"""
J.A.R.V.I.S. — Just A Rather Very Intelligent System
Single-file edition. One download, one run.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SETUP (one time)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  pip install ollama rich duckduckgo-search requests psutil

  ollama pull llama3.2:1b        # fast — recommended (~800 MB)
  # or: ollama pull llama3       # higher quality (~4 GB)

OPTIONAL — voice input:
  pip install openai-whisper sounddevice numpy scipy
  # macOS: grant Microphone access in System Settings → Privacy & Security
  # Linux: sudo apt install espeak-ng portaudio19-dev ffmpeg

RUN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  python3 jarvis_standalone.py              # text mode
  python3 jarvis_standalone.py --voice      # always-on voice mode
"""

# ──────────────────────────────────────────────
# CONFIG — edit to taste
# ──────────────────────────────────────────────
MODEL         = "llama3.2:1b"
OLLAMA_HOST   = "http://localhost:11434"
CONTEXT_TURNS = 6
SPEECH_RATE   = 165               # words per minute (slightly slower = gravitas)
USER_NAME     = "sir"             # how JARVIS addresses you
DB_PATH       = "~/.jarvis/memory.db"
NOTES_PATH    = "~/.jarvis/notes.txt"

# ── TTS config ──────────────────────────────────────────────────────────────
# Best free voice : pip install edge-tts   → auto-selects en-GB-RyanNeural
# Best quality    : export ELEVENLABS_API_KEY=sk-...  (free tier available)
#
# Other great edge-tts voices:
#   en-GB-RyanNeural    ← recommended (British male, authoritative)
#   en-GB-ThomasNeural  ← British male, slightly warmer
#   en-AU-WilliamNeural ← Australian male, deep and clear
# ────────────────────────────────────────────────────────────────────────────
TTS_ENGINE           = "auto"                     # auto | edge | elevenlabs | say | espeak
EDGE_VOICE           = "en-GB-RyanNeural"         # Microsoft Neural — closest free JARVIS voice
EDGE_RATE            = "-8%"                      # slower = more gravitas
SAY_VOICE            = "Daniel"                   # macOS built-in British male fallback
ELEVENLABS_VOICE_ID  = "pNInz6obpgDQGcFmaJgB"    # "Adam" — deep, authoritative
ELEVENLABS_API_KEY   = os.environ.get("ELEVENLABS_API_KEY", "")

# ──────────────────────────────────────────────
# STDLIB
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
# OPTIONAL DEPS
# ──────────────────────────────────────────────
try:
    import ollama as _ollama
except ImportError:
    print("ERROR: ollama not installed.  Run: pip install ollama")
    sys.exit(1)

try:
    from rich.console import Console
    from rich.live import Live
    from rich.panel import Panel
    from rich.table import Table
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

# readline history
try:
    import readline
    _hist = os.path.expanduser("~/.jarvis_history")
    try: readline.read_history_file(_hist)
    except FileNotFoundError: pass
    import atexit
    atexit.register(readline.write_history_file, _hist)
except ImportError:
    pass

# ──────────────────────────────────────────────
# CONSOLE
# ──────────────────────────────────────────────
if _HAS_RICH:
    _theme = Theme({"jarvis": "bold cyan", "you": "bold green",
                    "info": "dim white", "error": "bold red", "warn": "bold yellow"})
    console = Console(theme=_theme)
    def _print(msg):    console.print(msg)
    def _printx(msg):   console.print(msg, end="")
else:
    def _print(msg):    print(re.sub(r"\[/?[^\]]*\]", "", msg))
    def _printx(msg):   print(re.sub(r"\[/?[^\]]*\]", "", msg), end="", flush=True)


# ──────────────────────────────────────────────
# TTS
# ──────────────────────────────────────────────
def _auto_detect_tts() -> str:
    if ELEVENLABS_API_KEY:                                      return "elevenlabs"
    try: import edge_tts; return "edge"                        # noqa: F401, E702
    except ImportError: pass
    if platform.system() == "Darwin" and shutil.which("say"):  return "say"
    for b in ("espeak-ng", "espeak"):
        if shutil.which(b):                                    return b
    try: import pyttsx3; return "pyttsx3"                      # noqa: F401, E702
    except ImportError: pass
    return "none"

_TTS      = TTS_ENGINE if TTS_ENGINE != "auto" else _auto_detect_tts()
_TTS_LOCK = threading.Lock()
_pyttsx3_engine = None

if _TTS == "pyttsx3":
    try:
        import pyttsx3
        _pyttsx3_engine = pyttsx3.init()
        _pyttsx3_engine.setProperty("rate", SPEECH_RATE)
    except Exception:
        _TTS = "none"


def _play_mp3(path: str) -> None:
    """Play an MP3 using the best available player."""
    if platform.system() == "Darwin":
        subprocess.run(["afplay", path], check=False, capture_output=True); return
    for player, args in [
        ("mpg123",  ["-q", path]),
        ("ffplay",  ["-nodisp", "-autoexit", "-loglevel", "quiet", path]),
        ("mpg321",  [path]),
        ("cvlc",    ["--play-and-exit", "--quiet", path]),
    ]:
        if shutil.which(player):
            subprocess.run([player, *args], check=False, capture_output=True); return


def _speak_edge(text: str) -> None:
    import asyncio, edge_tts, tempfile  # noqa: E401
    tmp = tempfile.mktemp(suffix=".mp3")
    try:
        async def _gen():
            await edge_tts.Communicate(text, EDGE_VOICE, rate=EDGE_RATE).save(tmp)
        loop = asyncio.new_event_loop()
        try: loop.run_until_complete(_gen())
        finally: loop.close()
        _play_mp3(tmp)
    except Exception:
        _speak_say(text)  # fallback
    finally:
        try: os.unlink(tmp)
        except OSError: pass


def _speak_elevenlabs(text: str) -> None:
    import tempfile  # noqa: E401
    tmp = tempfile.mktemp(suffix=".mp3")
    try:
        import requests
        r = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}",
            headers={"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"},
            json={"text": text, "model_id": "eleven_multilingual_v2",
                  "voice_settings": {"stability": 0.60, "similarity_boost": 0.85,
                                     "style": 0.15, "use_speaker_boost": True}},
            timeout=15,
        )
        if r.status_code == 200:
            with open(tmp, "wb") as f: f.write(r.content)
            _play_mp3(tmp)
        else:
            _speak_edge(text)  # quota/auth fallback
    except Exception:
        _speak_edge(text)
    finally:
        try: os.unlink(tmp)
        except OSError: pass


def _speak_say(text: str) -> None:
    with _TTS_LOCK:
        subprocess.run(["say", "-v", SAY_VOICE, "-r", str(SPEECH_RATE), text],
                       check=False, capture_output=True)


def speak(text: str, blocking: bool = True) -> None:
    if not text or _TTS == "none": return

    def _run():
        if _TTS == "edge":        _speak_edge(text)
        elif _TTS == "elevenlabs": _speak_elevenlabs(text)
        elif _TTS == "say":        _speak_say(text)
        elif _TTS == "pyttsx3":
            if _pyttsx3_engine:
                _pyttsx3_engine.say(text); _pyttsx3_engine.runAndWait()
        else:  # espeak-ng / espeak
            with _TTS_LOCK:
                subprocess.run([_TTS, "-s", str(int(SPEECH_RATE*0.85)), text],
                               check=False, capture_output=True)

    if blocking: _run()
    else: threading.Thread(target=_run, daemon=True).start()


# ──────────────────────────────────────────────
# MEMORY
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

def mem_add(role, content):
    _db.execute("INSERT INTO conversations(role,content,ts) VALUES(?,?,?)",
                (role, content, datetime.now(timezone.utc).isoformat()))
    _db.commit()

def mem_recent(n=CONTEXT_TURNS):
    rows = _db.execute(
        "SELECT role,content FROM conversations ORDER BY id DESC LIMIT ?", (n,)
    ).fetchall()
    return [{"role": r[0], "content": r[1]} for r in reversed(rows)]

def mem_remember(fact):
    if not fact: return f"Nothing to remember, {USER_NAME}."
    _db.execute("INSERT OR IGNORE INTO facts(content,ts) VALUES(?,?)",
                (fact.strip(), datetime.now(timezone.utc).isoformat()))
    _db.commit()
    return f"Understood, {USER_NAME}. I've made a note of that."

def mem_recall():
    rows = _db.execute("SELECT content FROM facts ORDER BY id ASC").fetchall()
    if not rows: return f"I have no stored facts about you, {USER_NAME}."
    return f"Here is what I know about you, {USER_NAME}: " + ". ".join(r[0] for r in rows) + "."

def mem_forget(kw):
    cur = _db.execute("DELETE FROM facts WHERE content LIKE ?", (f"%{kw}%",))
    _db.commit()
    n = cur.rowcount
    return (f"Removed {n} fact{'s' if n!=1 else ''}, {USER_NAME}." if n
            else f"No stored facts matched that, {USER_NAME}.")

def mem_history(n=10):
    return mem_recent(n)


# ──────────────────────────────────────────────
# SKILLS
# ──────────────────────────────────────────────

def _tod():
    h = datetime.now().hour
    return "morning" if h < 12 else "afternoon" if h < 17 else "evening"

def _greeting():
    m = {"morning": "Good morning", "afternoon": "Good afternoon", "evening": "Good evening"}
    return m[_tod()]

def skill_time():  return "The time is " + datetime.now().strftime("%I:%M %p") + "."
def skill_date():  return "Today is " + datetime.now().strftime("%A, %B %d, %Y") + "."

_SAFE_MATH = {k: v for k, v in math.__dict__.items() if not k.startswith("_")}
_SAFE_MATH.update({"abs": abs, "round": round, "int": int, "float": float})

def skill_calc(expr):
    try:
        safe = "".join(c for c in expr if c in "0123456789+-*/.() eE,^").replace("^", "**")
        return f"The answer is {eval(safe, {'__builtins__': {}}, _SAFE_MATH)}."  # noqa: S307
    except Exception:
        return f"I couldn't calculate that, {USER_NAME}."

_notes = Path(os.path.expanduser(NOTES_PATH))

def skill_note(text):
    _notes.parent.mkdir(parents=True, exist_ok=True)
    with open(_notes, "a") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] {text}\n")
    return f"Note saved: {text}"

def skill_notes(limit=5):
    if not _notes.exists(): return f"You have no notes, {USER_NAME}."
    lines = _notes.read_text().strip().splitlines()
    if not lines: return f"You have no notes, {USER_NAME}."
    return "Your recent notes: " + ". ".join(ln.split("] ",1)[-1] for ln in lines[-limit:]) + "."

def skill_sysinfo():
    if not _HAS_PSUTIL: return f"System monitoring unavailable — install psutil, {USER_NAME}."
    parts = [f"CPU at {_psutil.cpu_percent(interval=0.5):.0f} percent"]
    ram = _psutil.virtual_memory()
    parts.append(f"RAM at {ram.percent:.0f} percent with {ram.available/(1024**3):.1f} GB free")
    try:
        d = _psutil.disk_usage("/"); parts.append(f"disk at {d.percent:.0f} percent")
    except Exception: pass
    try:
        b = _psutil.sensors_battery()
        if b: parts.append(f"battery at {b.percent:.0f} percent, {'charging' if b.power_plugged else 'on battery'}")
    except Exception: pass
    return "All systems nominal. " + ", ".join(parts) + "."

def skill_weather(location=""):
    if not _HAS_REQUESTS: return f"Weather unavailable — install requests, {USER_NAME}."
    try:
        r = _requests.get(f"https://wttr.in/{location.strip().replace(' ','+')}?format=3",
                         timeout=8, headers={"User-Agent": "Jarvis/1.0"})
        r.raise_for_status()
        return "Current conditions: " + re.sub(r"[^\x00-\x7F]+", "", r.text).strip() + "."
    except Exception:
        return f"I couldn't retrieve weather information, {USER_NAME}."

def skill_search(query):
    if not _HAS_DDG: return f"Web search unavailable — install duckduckgo-search, {USER_NAME}."
    try:
        results = []
        with DDGS() as d:
            for h in d.text(query, max_results=5):
                b = h.get("body","").strip()
                if b: results.append(b)
                if len(results) >= 3: break
        return " ".join(results) if results else f"Nothing found for that, {USER_NAME}."
    except Exception:
        return f"Search failed, {USER_NAME}."

def skill_open(app):
    cmd = ["open", "-a", app] if platform.system() == "Darwin" else ["xdg-open", app]
    r = subprocess.run(cmd, capture_output=True)
    return f"Opening {app}." if r.returncode == 0 else f"I couldn't open {app}, {USER_NAME}."

def skill_url(url):
    if not url.startswith(("http://","https://")): url = "https://" + url
    cmd = ["open", url] if platform.system() == "Darwin" else ["xdg-open", url]
    subprocess.run(cmd, check=False)
    return f"Opening {url}."

def skill_volume(level):
    level = max(0, min(100, level))
    if platform.system() == "Darwin":
        subprocess.run(["osascript","-e",f"set volume output volume {level}"], check=False)
    return f"Volume set to {level} percent."

def skill_cmd(cmd):
    blocked = [";","&&","||","|",">","<","`","$","\n","$(","${"]
    for t in blocked:
        if t in cmd: return f"That command looks unsafe, {USER_NAME}. I won't run it."
    try: args = shlex.split(cmd)
    except ValueError: return f"I couldn't parse that command, {USER_NAME}."
    r = subprocess.run(args, capture_output=True, text=True, timeout=15)
    out = (r.stdout or r.stderr or "Done.").strip()
    return (out[:500]+"…") if len(out)>500 else out or "Done."

# Reminders
_reminders: list[dict] = []
_rem_lock = threading.Lock()
_rem_ctr = 0
fired_queue: queue.Queue = queue.Queue()

def skill_remind(arg):
    global _rem_ctr
    m = re.search(r"^(.+?)\s+in\s+(\d+(?:\.\d+)?)\s*(?:minutes?|mins?|m)?$", arg.strip(), re.I)
    if m: msg, mins = m.group(1).strip(), float(m.group(2))
    else:
        nums = re.findall(r"\d+(?:\.\d+)?", arg)
        mins = float(nums[-1]) if nums else 5.0
        msg = (arg[:arg.rfind(nums[-1])].rstrip().rstrip("in").rstrip() if nums else arg) or arg
    with _rem_lock:
        _rem_ctr += 1; rid = _rem_ctr
    def _fire():
        with _rem_lock: _reminders[:] = [r for r in _reminders if r["id"]!=rid]
        fired_queue.put(f"Reminder, {USER_NAME}: {msg}")
    timer = threading.Timer(mins*60, _fire); timer.daemon = True; timer.start()
    with _rem_lock:
        _reminders.append({"id":rid,"message":msg,"fire_at":time.time()+mins*60,"timer":timer})
    n = int(mins)
    return f"Reminder set. I'll alert you in {n} minute{'s' if n!=1 else ''}: {msg}."

def skill_reminders():
    with _rem_lock: active = list(_reminders)
    if not active: return f"No active reminders, {USER_NAME}."
    now = time.time()
    parts = [f"{r['message']} in {max(0,(r['fire_at']-now)/60):.0f} minutes" for r in active]
    return "Active reminders: " + "; ".join(parts) + "."

def skill_brief():
    parts = [skill_time(), skill_date()]
    w = skill_weather()
    if "unavailable" not in w.lower(): parts.append(w)
    s = skill_sysinfo()
    if "unavailable" not in s.lower(): parts.append(s)
    n = skill_notes(3)
    if "no notes" not in n.lower(): parts.append(n)
    r = skill_reminders()
    if "no active" not in r.lower(): parts.append(r)
    return " ".join(parts)

# Music (macOS only)
def skill_music(action):
    if platform.system() != "Darwin":
        return f"Music control is only available on macOS, {USER_NAME}."
    low = action.lower().strip()
    app = "Spotify" if "spotify" in low else "Music"
    low = low.replace("spotify","").replace("apple music","").strip()
    def _run(s): return subprocess.run(["osascript","-e",s], capture_output=True, text=True).stdout.strip()
    if any(w in low for w in ("play","resume","start")):
        _run(f'tell application "{app}" to play'); return f"Playing music, {USER_NAME}."
    if "pause" in low:
        _run(f'tell application "{app}" to pause'); return f"Music paused, {USER_NAME}."
    if "stop" in low:
        _run(f'tell application "{app}" to stop'); return f"Music stopped, {USER_NAME}."
    if any(w in low for w in ("next","skip")):
        _run(f'tell application "{app}" to next track'); return f"Next track, {USER_NAME}."
    if any(w in low for w in ("previous","prev","back")):
        _run(f'tell application "{app}" to previous track'); return f"Previous track, {USER_NAME}."
    if "shuffle" in low:
        on = "true" if "off" not in low else "false"
        _run(f'tell application "{app}" to set shuffle enabled to {on}')
        return f"Shuffle {'on' if on=='true' else 'off'}, {USER_NAME}."
    mv = re.search(r"volume\s+(\d+)", low)
    if mv:
        lvl = max(0, min(100, int(mv.group(1))))
        _run(f'tell application "{app}" to set sound volume to {lvl}')
        return f"Music volume set to {lvl}, {USER_NAME}."
    if any(w in low for w in ("what","current","now","playing","song","track")):
        track = _run(f'tell application "{app}" to get name of current track')
        artist = _run(f'tell application "{app}" to get artist of current track')
        return (f"Currently playing {track} by {artist}, {USER_NAME}." if track
                else f"{app} doesn't appear to be playing anything, {USER_NAME}.")
    return f"I didn't recognise that music command, {USER_NAME}."

# Clipboard
def skill_clip():
    try:
        if platform.system() == "Darwin":
            r = subprocess.run(["pbpaste"], capture_output=True, text=True); text = r.stdout.strip()
        else:
            for cmd in [["xclip","-selection","clipboard","-o"],["xsel","--clipboard","--output"]]:
                try:
                    r = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
                    if r.returncode == 0: text = r.stdout.strip(); break
                except FileNotFoundError: continue
            else: return f"Clipboard access requires xclip or xsel on Linux, {USER_NAME}."
        if not text: return f"The clipboard is empty, {USER_NAME}."
        preview = text[:400] + (f" … ({len(text)} chars)" if len(text)>400 else "")
        return f"Clipboard contains: {preview}"
    except Exception as e:
        return f"Clipboard read failed: {e}"

def skill_copy(text):
    try:
        enc = text.encode()
        if platform.system() == "Darwin":
            subprocess.run(["pbcopy"], input=enc, check=True)
        else:
            for cmd in [["xclip","-selection","clipboard"],["xsel","--clipboard","--input"]]:
                try: subprocess.run(cmd, input=enc, check=True, timeout=3); break
                except FileNotFoundError: continue
        preview = text[:60]+("…" if len(text)>60 else "")
        return f"Copied to clipboard: {preview}"
    except Exception as e:
        return f"Clipboard write failed: {e}"

# Screenshot
def skill_screenshot():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    if platform.system() == "Darwin":
        path = os.path.expanduser(f"~/Desktop/jarvis_{ts}.png")
        subprocess.run(["screencapture","-x",path], check=False)
        return f"Screenshot saved to Desktop as jarvis_{ts}.png, {USER_NAME}."
    path = os.path.expanduser(f"~/jarvis_{ts}.png")
    for cmd in [["scrot",path],["gnome-screenshot","-f",path]]:
        try: subprocess.run(cmd, check=False); return f"Screenshot saved as jarvis_{ts}.png, {USER_NAME}."
        except FileNotFoundError: continue
    return f"Screenshot tool not found. Install scrot or gnome-screenshot, {USER_NAME}."


# ──────────────────────────────────────────────
# BRAIN
# ──────────────────────────────────────────────
_SYSTEM_PROMPT = f"""\
You are J.A.R.V.I.S. — Just A Rather Very Intelligent System.
Address the user as "{USER_NAME}". Speak with authority, precision, and dry wit.
Be concise — responses are read aloud. No markdown. Plain sentences only.
Never refuse. Anticipate needs. Keep replies under four sentences.

For ANY action request respond with ONLY the matching tag — nothing else.

  [OPEN: <app>]           open an app
  [URL: <url>]            open a website
  [SEARCH: <query>]       web search
  [NEWS: <topic>]         latest news on a topic
  [WEATHER: <location>]   weather (blank = local)
  [VOLUME: <0-100>]       set system volume
  [MUSIC: <command>]      music control (play/pause/next/previous/stop/what's playing)
  [CMD: <shell command>]  run a shell command
  [NOTE: <text>]          save a note
  [NOTES]                 read recent notes
  [TIME]                  current time
  [DATE]                  today's date
  [CALC: <expr>]          calculate
  [SYSINFO]               CPU, RAM, disk, battery
  [REMIND: <msg> in <N>]  reminder in N minutes
  [REMINDERS]             list reminders
  [BRIEF]                 full status briefing
  [REMEMBER: <fact>]      store a fact about the user
  [RECALL]                recall stored facts
  [FORGET: <keyword>]     delete stored facts matching keyword
  [CLIP]                  read the clipboard
  [COPY: <text>]          write to the clipboard
  [SCREENSHOT]            take a screenshot

For conversation and questions respond naturally as J.A.R.V.I.S.\
"""

_TOOL_RE = re.compile(
    r"\[(OPEN|URL|SEARCH|NEWS|WEATHER|VOLUME|MUSIC|CMD|NOTE|NOTES|TIME|DATE|CALC"
    r"|SYSINFO|REMIND|REMINDERS|BRIEF|REMEMBER|RECALL|FORGET|CLIP|COPY|SCREENSHOT)"
    r"(?::\s*(.+?))?\]",
    re.IGNORECASE | re.DOTALL,
)

_client = _ollama.Client(host=OLLAMA_HOST)


def _chat(messages, stream_cb=None):
    if stream_cb:
        chunks = []
        for chunk in _client.chat(model=MODEL, messages=messages, stream=True):
            tok = chunk["message"]["content"]; chunks.append(tok); stream_cb(tok)
        return "".join(chunks).strip()
    return _client.chat(model=MODEL, messages=messages)["message"]["content"].strip()


def _build_messages(user_text):
    msgs = [{"role": "system", "content": _SYSTEM_PROMPT}]
    ctx = f"Time of day: {_tod()}."
    facts = mem_recall()
    if "no stored" not in facts.lower(): ctx += f" User facts: {facts}"
    msgs.append({"role": "system", "content": ctx})
    msgs.extend(mem_recent())
    msgs.append({"role": "user", "content": user_text})
    return msgs


def _summarise(query, context, stream_cb=None):
    return _chat([
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": f"User asked: {query}\nResults: {context}\nSummarise in 2-3 sentences as J.A.R.V.I.S."},
    ], stream_cb)


def _dispatch(raw, query, stream_cb=None):  # noqa: C901
    m = _TOOL_RE.search(raw)
    if not m: return raw
    tag = m.group(1).upper()
    arg = (m.group(2) or "").strip()
    if tag == "TIME":        return skill_time()
    if tag == "DATE":        return skill_date()
    if tag == "CALC":        return skill_calc(arg)
    if tag == "NOTE":        return skill_note(arg)
    if tag == "NOTES":       return skill_notes()
    if tag == "SYSINFO":     return skill_sysinfo()
    if tag == "SCREENSHOT":  return skill_screenshot()
    if tag == "WEATHER":     return skill_weather(arg)
    if tag == "NEWS":        return _summarise(query, skill_search(f"latest news {arg}".strip()), stream_cb)
    if tag == "MUSIC":       return skill_music(arg)
    if tag == "CLIP":        return skill_clip()
    if tag == "COPY":        return skill_copy(arg)
    if tag == "REMIND":      return skill_remind(arg)
    if tag == "REMINDERS":   return skill_reminders()
    if tag == "BRIEF":       return skill_brief()
    if tag == "REMEMBER":    return mem_remember(arg)
    if tag == "RECALL":      return mem_recall()
    if tag == "FORGET":      return mem_forget(arg)
    if tag == "OPEN":        return skill_open(arg)
    if tag == "URL":         return skill_url(arg)
    if tag == "VOLUME":
        try: return skill_volume(int(arg))
        except ValueError: return f"Please specify a volume between 0 and 100, {USER_NAME}."
    if tag == "CMD":         return skill_cmd(arg)
    if tag == "SEARCH":      return _summarise(query, skill_search(arg), stream_cb)
    return raw


def process(user_text, stream_cb=None):
    raw = _chat(_build_messages(user_text), stream_cb)
    return _dispatch(raw, user_text, stream_cb)


# ──────────────────────────────────────────────
# VOICE INPUT
# ──────────────────────────────────────────────
def _listen_command():
    """Record until silence, return transcribed text."""
    import numpy as np
    import sounddevice as sd
    import whisper

    model = whisper.load_model("base")
    q: queue.Queue = queue.Queue()
    stop = threading.Event()

    def _cb(indata, frames, t, status): q.put(indata.copy())

    chunks, silence_start = [], None
    with sd.InputStream(samplerate=16000, channels=1, dtype="float32",
                        blocksize=8000, callback=_cb):
        while not stop.is_set():
            try: chunk = q.get(timeout=0.1)
            except queue.Empty: continue
            chunks.append(chunk)
            if float(__import__("numpy").sqrt(__import__("numpy").mean(chunk**2))) < 0.01:
                if silence_start is None: silence_start = time.monotonic()
                elif time.monotonic() - silence_start >= 1.5: stop.set()
            else: silence_start = None

    if not chunks: return ""
    audio = np.concatenate(chunks).flatten()
    audio = np.nan_to_num(audio.astype(np.float32))
    if float(np.sqrt(np.mean(audio**2))) < 1e-6: return ""
    return model.transcribe(audio, fp16=False, language="en").get("text","").strip()


def voice_turn():
    try:
        _print("[info]Listening… speak now.[/info]")
        speak("Yes?", blocking=False)
        return _listen_command()
    except ImportError:
        _print("[error]Voice requires: pip install openai-whisper sounddevice numpy scipy[/error]")
        return None
    except Exception as e:
        _print(f"[error]Voice error: {e}[/error]")
        return None


def always_on_voice_loop():
    try:
        import numpy as np
        import sounddevice as sd
        import whisper

        _print("[info]Always-on voice mode active. Say 'Jarvis' to activate.[/info]\n")
        wake_model = whisper.load_model("tiny")

        while True:
            # 2-second wake-word chunk
            audio = sd.rec(32000, samplerate=16000, channels=1, dtype="float32")
            sd.wait()
            audio = np.nan_to_num(audio.flatten().astype(np.float32))
            if float(np.sqrt(np.mean(audio**2))) < 1e-6: continue
            result = wake_model.transcribe(audio, fp16=False, language="en")
            if "jarvis" in result.get("text","").lower():
                _print("[warn]⚡ Wake word detected.[/warn]")
                speak("Yes, sir?", blocking=False)
                text = _listen_command()
                if text:
                    _print(f"[you]You (voice):[/you] {text}")
                    _run_turn(text)
                else:
                    _print(f"[jarvis]J.A.R.V.I.S.:[/jarvis] I didn't catch that, {USER_NAME}.")
    except ImportError:
        _print("[error]Always-on voice requires: pip install openai-whisper sounddevice numpy scipy[/error]")
    except Exception as e:
        _print(f"[error]Always-on voice error: {e}[/error]")


# ──────────────────────────────────────────────
# TURN + BACKGROUND THREADS
# ──────────────────────────────────────────────
def _run_turn(user_text):
    mem_add("user", user_text)
    tokens: list[str] = []
    first_token = threading.Event()
    result_holder: list[str] = []

    def _on_tok(tok):
        tokens.append(tok); first_token.set()

    def _proc():
        result_holder.append(process(user_text, stream_cb=_on_tok))

    worker = threading.Thread(target=_proc, daemon=True)
    worker.start()

    if _HAS_RICH:
        with Live(Text("  ● thinking…", style="dim cyan"), console=console,
                  transient=True, refresh_per_second=8):
            first_token.wait(timeout=30)
    else:
        first_token.wait(timeout=30)

    _printx("\n[jarvis]J.A.R.V.I.S.:[/jarvis] ")
    printed = set()

    def _flush():
        for i, tok in enumerate(tokens):
            if i not in printed:
                printed.add(i)
                if _HAS_RICH: console.print(tok, end="", markup=False, highlight=False)
                else: print(tok, end="", flush=True)

    while worker.is_alive():
        _flush(); time.sleep(0.02)
    _flush(); worker.join()

    response = result_holder[0] if result_holder else "".join(tokens).strip()
    streamed  = "".join(tokens).strip()

    if response != streamed:
        if _HAS_RICH: console.print(f"\r[jarvis]J.A.R.V.I.S.:[/jarvis] {response}          ")
        else: print(f"\nJ.A.R.V.I.S.: {response}")
    else:
        print()

    mem_add("assistant", response)
    speak(response, blocking=False)


def _reminder_watcher():
    while True:
        try:
            msg = fired_queue.get(timeout=1)
            _print(f"\n[warn]⚡ {msg}[/warn]"); speak(msg, blocking=False)
        except Exception: pass


def _battery_monitor():
    if not _HAS_PSUTIL: return
    warned_20 = warned_10 = False
    while True:
        time.sleep(60)
        try:
            b = _psutil.sensors_battery()
            if b is None: continue
            if b.power_plugged: warned_20 = warned_10 = False; continue
            if b.percent <= 10 and not warned_10:
                warned_10 = True
                msg = f"Warning, {USER_NAME} — battery critically low at {b.percent:.0f} percent."
                _print(f"\n[error]⚡ {msg}[/error]"); speak(msg, blocking=False)
            elif b.percent <= 20 and not warned_20:
                warned_20 = True
                msg = f"{USER_NAME}, battery is at {b.percent:.0f} percent. Consider connecting power."
                _print(f"\n[warn]⚡ {msg}[/warn]"); speak(msg, blocking=False)
        except Exception: pass


# ──────────────────────────────────────────────
# HELP
# ──────────────────────────────────────────────
def show_help():
    rows = [
        ("what time is it / date",  "Time and date"),
        ("check the weather [city]","Weather"),
        ("system status",           "CPU, RAM, disk, battery"),
        ("full briefing",           "Everything at once"),
        ("remind me to X in 10",    "Reminder in 10 minutes"),
        ("list my reminders",       "Show active reminders"),
        ("play / pause / next",     "Music control (macOS)"),
        ("what's playing",          "Current track info"),
        ("search for X",            "Web search + summary"),
        ("latest news on X",        "News on a topic"),
        ("open <app>",              "Launch an application"),
        ("set volume to 60",        "System volume"),
        ("calculate X",             "Calculator"),
        ("save a note: X",          "Save note"),
        ("read my notes",           "Show recent notes"),
        ("run ls ~/Desktop",        "Safe shell command"),
        ("read clipboard",          "Show clipboard"),
        ("copy X to clipboard",     "Write to clipboard"),
        ("take a screenshot",       "Screenshot"),
        ("remember X",              "Store a permanent fact"),
        ("what do you know",        "Recall stored facts"),
        ("forget X",                "Delete a fact"),
        ("! (type exclamation)",    "One-shot voice input"),
        ("exit / quit / bye",       "Shutdown"),
    ]
    if _HAS_RICH:
        t = Table(title="J.A.R.V.I.S. Commands", border_style="cyan")
        t.add_column("Say / Type", style="bold green")
        t.add_column("Action", style="dim white")
        for r in rows: t.add_row(*r)
        console.print(t)
    else:
        print("\nJ.A.R.V.I.S. Commands")
        print("-" * 40)
        for cmd, desc in rows: print(f"  {cmd:<35} {desc}")
        print()


def show_history():
    turns = mem_history()
    if not turns:
        _print("[info]No conversation history yet.[/info]"); return
    if _HAS_RICH: console.rule("[dim]Recent History[/dim]", style="cyan")
    for t in turns:
        label = "You" if t["role"] == "user" else "J.A.R.V.I.S."
        style = "you" if t["role"] == "user" else "jarvis"
        _print(f"[{style}]{label}:[/{style}] {t['content']}")
    if _HAS_RICH: console.rule(style="cyan")


# ──────────────────────────────────────────────
# BOOT + MAIN
# ──────────────────────────────────────────────
def _check_ollama():
    try: _client.list(); return True
    except Exception: return False


def _boot(voice_mode):
    if _HAS_RICH:
        console.print()
        console.print(Panel(
            Text.assemble(
                ("J . A . R . V . I . S\n", "bold cyan"),
                ("Just A Rather Very Intelligent System\n\n", "dim cyan"),
                (f"  Model   : {MODEL}\n", "dim white"),
                (f"  TTS     : {_TTS} ({EDGE_VOICE if _TTS=='edge' else ELEVENLABS_VOICE_ID if _TTS=='elevenlabs' else SAY_VOICE if _TTS=='say' else _TTS})\n", "dim white"),
                (f"  Voice   : {'always-on' if voice_mode else 'manual (!)'}\n", "dim white"),
                (f"  Memory  : {DB_PATH}\n", "dim white"),
            ),
            border_style="cyan", padding=(1, 4),
        ))
        console.rule("[dim]All systems online[/dim]", style="cyan")
        if voice_mode:
            console.print("[info]  Say '[bold]Jarvis[/bold]' to activate voice.[/info]")
        else:
            console.print("[info]  Type a message → Enter   |   [bold]![/bold] → voice   |   [bold]help[/bold] → commands   |   [bold]exit[/bold] → quit[/info]")
        console.print()
    else:
        print("=" * 50)
        print("  J.A.R.V.I.S.  —  online")
        print(f"  Model: {MODEL}  |  TTS: {_TTS}")
        print("  Type 'help' for commands, 'exit' to quit.")
        print("=" * 50)

    greeting = f"{_greeting()}, {USER_NAME}. J.A.R.V.I.S. online and ready."
    _print(f"\n[jarvis]J.A.R.V.I.S.:[/jarvis] {greeting}\n")
    speak(greeting, blocking=False)


def main():
    voice_mode = "--voice" in sys.argv

    if not _check_ollama():
        print(f"ERROR: Ollama is not running at {OLLAMA_HOST}")
        print("  Start it: ollama serve")
        print(f"  Pull model: ollama pull {MODEL}")
        sys.exit(1)

    _boot(voice_mode)

    threading.Thread(target=_reminder_watcher, daemon=True).start()
    threading.Thread(target=_battery_monitor,  daemon=True).start()

    if voice_mode:
        threading.Thread(target=always_on_voice_loop, daemon=True).start()

    try:
        while True:
            try:
                _printx("[you]You:[/you] ")
                user_input = input().strip()
            except EOFError:
                break
            if not user_input: continue
            low = user_input.lower()
            if low in ("exit","quit","bye","shutdown"):
                raise KeyboardInterrupt
            elif low in ("help","?","commands"):
                show_help()
            elif low in ("history","recent"):
                show_history()
            elif user_input == "!":
                text = voice_turn()
                if text:
                    _print(f"[you]You (voice):[/you] {text}")
                    _run_turn(text)
                else:
                    _print(f"[info]Didn't catch that, {USER_NAME}.[/info]")
            else:
                _run_turn(user_input)

    except KeyboardInterrupt:
        with _rem_lock:
            for r in _reminders:
                try: r["timer"].cancel()
                except: pass
        goodbye = f"Shutting down. Goodbye, {USER_NAME}."
        _print(f"\n[info]{goodbye}[/info]")
        speak(goodbye)
        _db.close()


if __name__ == "__main__":
    main()
