"""J.A.R.V.I.S. — entry point.

Usage
-----
  python3 src/jarvis/main.py            text mode (default)
  python3 src/jarvis/main.py --voice    always-on voice mode
"""

import os
import sys
import threading
import time

import yaml
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from jarvis.core.brain import Brain
from jarvis.core.speaker import Speaker
from jarvis.memory.conversation import ConversationMemory
from jarvis.skills import reminders as reminder_module

# ------------------------------------------------------------------
# readline history (best-effort)
# ------------------------------------------------------------------
try:
    import readline
    _HISTORY = os.path.expanduser("~/.jarvis_history")
    try:
        readline.read_history_file(_HISTORY)
    except FileNotFoundError:
        pass
    import atexit
    atexit.register(readline.write_history_file, _HISTORY)
except ImportError:
    pass

# ------------------------------------------------------------------
# Rich theme & console
# ------------------------------------------------------------------
_THEME = Theme({
    "jarvis": "bold cyan",
    "you":    "bold green",
    "info":   "dim white",
    "error":  "bold red",
    "warn":   "bold yellow",
    "dim":    "dim cyan",
})
console = Console(theme=_THEME)


# ------------------------------------------------------------------
# Config
# ------------------------------------------------------------------

def load_config() -> dict:
    config_path = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "..", "config", "settings.yaml")
    )
    with open(config_path) as f:
        return yaml.safe_load(f)


def check_ollama(brain: Brain) -> bool:
    try:
        import ollama
        ollama.Client(host=brain.host).list()
        return True
    except Exception:
        return False


def _time_greeting() -> str:
    h = __import__("datetime").datetime.now().hour
    if 5 <= h < 12:   return "Good morning"
    if 12 <= h < 17:  return "Good afternoon"
    return "Good evening"


# ------------------------------------------------------------------
# Boot sequence
# ------------------------------------------------------------------

def boot_sequence(config: dict, speaker: Speaker, voice_mode: bool) -> None:
    user_name = config.get("jarvis", {}).get("user_name", "sir")

    console.print()
    console.print(Panel(
        Text.assemble(
            ("J . A . R . V . I . S\n", "bold cyan"),
            ("Just A Rather Very Intelligent System\n\n", "dim cyan"),
            (f"  Model   : {config.get('ollama', {}).get('model', 'llama3.2:1b')}\n", "dim white"),
            (f"  TTS     : {speaker.engine_name}\n", "dim white"),
            (f"  Voice   : {'always-on' if voice_mode else 'manual (!)'}\n", "dim white"),
            (f"  Memory  : active\n", "dim white"),
        ),
        border_style="cyan",
        padding=(1, 4),
    ))
    console.rule("[dim]All systems online[/dim]", style="cyan")

    if voice_mode:
        console.print(f"[info]  Say '[bold]Jarvis[/bold]' to activate voice input.[/info]")
    else:
        console.print("[info]  Type a message → Enter   |   [bold]![/bold] → voice input[/info]")
    console.print("[info]  [bold]help[/bold] → commands   [bold]history[/bold] → recent turns   [bold]exit[/bold] → quit[/info]\n")

    greeting = f"{_time_greeting()}, {user_name}. All systems are online and ready."
    console.print(f"[jarvis]J.A.R.V.I.S.:[/jarvis] {greeting}\n")
    speaker.speak(greeting, blocking=False)


# ------------------------------------------------------------------
# Help & history
# ------------------------------------------------------------------

def show_help() -> None:
    t = Table(title="J.A.R.V.I.S. Capabilities", border_style="cyan", show_header=True)
    t.add_column("Command / Say", style="bold green")
    t.add_column("Action", style="dim white")
    rows = [
        ("what time is it",         "Current time"),
        ("today's date",            "Today's date"),
        ("check the weather",       "Local weather"),
        ("check weather in London", "Weather for a city"),
        ("system status",           "CPU, RAM, disk, battery"),
        ("full briefing",           "Everything at once"),
        ("remind me to X in 10",    "Reminder in 10 minutes"),
        ("list my reminders",       "Show active reminders"),
        ("play music / pause",      "Music control (macOS)"),
        ("what's playing",          "Current track info"),
        ("search for X",            "Web search + summary"),
        ("latest news on X",        "News on a topic"),
        ("open Spotify",            "Launch an app"),
        ("set volume to 60",        "System volume"),
        ("calculate 15 * 8",        "Calculator"),
        ("save a note: X",          "Save note to disk"),
        ("read my notes",           "Show recent notes"),
        ("run ls ~/Desktop",        "Safe shell command"),
        ("read clipboard",          "Show clipboard contents"),
        ("copy X to clipboard",     "Write to clipboard"),
        ("take a screenshot",       "Screenshot to Desktop"),
        ("remember X about me",     "Store a permanent fact"),
        ("what do you know",        "Recall stored facts"),
        ("forget X",                "Delete a stored fact"),
        ("!",                       "One-shot voice input"),
        ("exit / quit / bye",       "Shut down J.A.R.V.I.S."),
    ]
    for cmd, desc in rows:
        t.add_row(cmd, desc)
    console.print(t)


def show_history(memory: ConversationMemory) -> None:
    turns = memory.get_recent(10)
    if not turns:
        console.print("[info]No conversation history yet.[/info]")
        return
    console.rule("[dim]Recent History[/dim]", style="cyan")
    for turn in turns:
        style = "you" if turn["role"] == "user" else "jarvis"
        label = "You" if turn["role"] == "user" else "J.A.R.V.I.S."
        console.print(f"[{style}]{label}:[/{style}] {turn['content']}")
    console.rule(style="cyan")


# ------------------------------------------------------------------
# Proactive battery monitor
# ------------------------------------------------------------------

def _battery_monitor(speaker: Speaker) -> None:
    """Warn proactively when battery is low (20% and 10%)."""
    warned_20 = False
    warned_10 = False
    try:
        import psutil
    except ImportError:
        return
    while True:
        time.sleep(60)
        try:
            bat = psutil.sensors_battery()
            if bat is None:
                continue
            if bat.power_plugged:
                warned_20 = warned_10 = False
                continue
            if bat.percent <= 10 and not warned_10:
                warned_10 = True
                msg = f"Warning, sir — battery is critically low at {bat.percent:.0f} percent. Please connect power immediately."
                console.print(f"\n[error]⚡ {msg}[/error]")
                speaker.speak(msg, blocking=False)
            elif bat.percent <= 20 and not warned_20:
                warned_20 = True
                msg = f"Sir, battery is at {bat.percent:.0f} percent. You may want to connect power."
                console.print(f"\n[warn]⚡ {msg}[/warn]")
                speaker.speak(msg, blocking=False)
        except Exception:
            pass


# ------------------------------------------------------------------
# Reminder watcher
# ------------------------------------------------------------------

def _watch_reminders(speaker: Speaker) -> None:
    while True:
        try:
            msg = reminder_module.fired_queue.get(timeout=1)
            console.print(f"\n[warn]⚡ {msg}[/warn]")
            speaker.speak(msg, blocking=False)
        except Exception:
            pass


# ------------------------------------------------------------------
# Conversation turn
# ------------------------------------------------------------------

def run_turn(
    user_text: str,
    brain: Brain,
    speaker: Speaker,
    memory: ConversationMemory,
) -> None:
    if not user_text.strip():
        return

    memory.add_message("user", user_text)

    tokens: list[str] = []
    first_token = threading.Event()
    result_holder: list[str] = []

    def _on_token(tok: str) -> None:
        tokens.append(tok)
        first_token.set()

    def _process() -> None:
        result_holder.append(brain.process(user_text, stream_callback=_on_token))

    worker = threading.Thread(target=_process, daemon=True)
    worker.start()

    # Show thinking spinner until first token arrives
    with Live(
        Text("  ● thinking…", style="dim cyan"),
        console=console,
        transient=True,
        refresh_per_second=8,
    ):
        first_token.wait(timeout=30)

    # Stream output
    console.print("\n[jarvis]J.A.R.V.I.S.:[/jarvis] ", end="")
    printed = set()

    def _flush() -> None:
        for i, tok in enumerate(tokens):
            if i not in printed:
                printed.add(i)
                console.print(tok, end="", markup=False, highlight=False)

    # Flush buffered tokens, then keep flushing as worker streams more
    while worker.is_alive():
        _flush()
        time.sleep(0.02)
    _flush()

    worker.join()
    response = result_holder[0] if result_holder else "".join(tokens).strip()
    streamed = "".join(tokens).strip()

    if response != streamed:
        console.print(f"\r[jarvis]J.A.R.V.I.S.:[/jarvis] {response}           ")
    else:
        console.print()

    memory.add_message("assistant", response)
    speaker.speak(response, blocking=False)


# ------------------------------------------------------------------
# Voice turns
# ------------------------------------------------------------------

def voice_turn(
    config: dict,
    brain: Brain,
    speaker: Speaker,
    memory: ConversationMemory,
) -> None:
    try:
        from jarvis.core.listener import Listener
        listener = Listener(config)
        console.print("[info]Listening… speak now.[/info]")
        speaker.speak("Yes, sir?", blocking=False)
        user_text = listener.transcribe_command()
        if user_text.strip():
            console.print(f"[you]You (voice):[/you] {user_text}")
            run_turn(user_text, brain, speaker, memory)
        else:
            console.print("[info]I didn't catch that, sir.[/info]")
    except Exception as e:
        console.print(f"[error]Voice error:[/error] {e}")


def always_on_voice_loop(
    config: dict,
    brain: Brain,
    speaker: Speaker,
    memory: ConversationMemory,
) -> None:
    """Continuously listen for wake word, then process commands."""
    try:
        from jarvis.core.listener import Listener
        listener = Listener(config)
        console.print("[info]Always-on voice mode active. Say 'Jarvis' to activate.[/info]\n")
        while True:
            listener.wait_for_wake_word()
            console.print("[warn]⚡ Wake word detected.[/warn]")
            speaker.speak("Yes, sir?", blocking=False)
            text = listener.transcribe_command()
            if text.strip():
                console.print(f"[you]You (voice):[/you] {text}")
                run_turn(text, brain, speaker, memory)
            else:
                response = "I didn't catch that, sir."
                console.print(f"[jarvis]J.A.R.V.I.S.:[/jarvis] {response}")
                speaker.speak(response, blocking=False)
    except ImportError:
        console.print(
            "[error]Voice requires:[/error] pip install openai-whisper sounddevice numpy scipy"
        )
    except Exception as e:
        console.print(f"[error]Always-on voice error:[/error] {e}")


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

def main() -> None:
    voice_mode = "--voice" in sys.argv

    config = load_config()
    speaker = Speaker(config)
    memory = ConversationMemory(config)
    brain = Brain(config, memory)
    user_name = config.get("jarvis", {}).get("user_name", "sir")

    if not check_ollama(brain):
        console.print(
            "[error]Ollama is not running.[/error]\n"
            "[info]  Start it: ollama serve[/info]\n"
            f"[info]  Pull model: ollama pull {brain.model}[/info]"
        )
        sys.exit(1)

    boot_sequence(config, speaker, voice_mode)

    # Background threads
    threading.Thread(target=_watch_reminders, args=(speaker,), daemon=True).start()
    threading.Thread(target=_battery_monitor, args=(speaker,), daemon=True).start()

    # Always-on voice runs in its own thread; text input continues below
    if voice_mode:
        threading.Thread(
            target=always_on_voice_loop,
            args=(config, brain, speaker, memory),
            daemon=True,
        ).start()

    try:
        while True:
            try:
                console.print("[you]You:[/you] ", end="")
                user_input = input().strip()
            except EOFError:
                break

            if not user_input:
                continue

            low = user_input.lower()

            if low in ("exit", "quit", "bye", "shutdown"):
                raise KeyboardInterrupt
            elif low in ("help", "?", "commands"):
                show_help()
            elif low in ("history", "recent"):
                show_history(memory)
            elif user_input == "!":
                voice_turn(config, brain, speaker, memory)
            else:
                run_turn(user_input, brain, speaker, memory)

    except KeyboardInterrupt:
        reminder_module.cancel_all()
        goodbye = f"Shutting down all systems. Goodbye, {user_name}."
        console.print(f"\n[info]{goodbye}[/info]")
        speaker.speak(goodbye)
        memory.close()


if __name__ == "__main__":
    main()
