"""J.A.R.V.I.S. — entry point.

Modes
-----
- Default : type commands at the prompt
- Voice   : type  !  and press Enter to activate one voice command
"""

import os
import sys
import threading

import yaml
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
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
# Rich theme
# ------------------------------------------------------------------
_THEME = Theme({
    "jarvis":  "bold cyan",
    "you":     "bold green",
    "info":    "dim white",
    "error":   "bold red",
    "warn":    "bold yellow",
    "dim":     "dim cyan",
    "status":  "bright_black",
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


# ------------------------------------------------------------------
# Boot sequence
# ------------------------------------------------------------------

def boot_sequence(config: dict, speaker: Speaker) -> None:
    """Display JARVIS-style boot sequence."""
    jarvis_cfg = config.get("jarvis", {})
    user_name = jarvis_cfg.get("user_name", "sir")

    console.print()
    console.print(Panel(
        Text.assemble(
            ("J . A . R . V . I . S\n", "bold cyan"),
            ("Just A Rather Very Intelligent System\n", "dim cyan"),
            ("\nInitializing all subsystems…", "dim white"),
        ),
        border_style="cyan",
        padding=(1, 4),
    ))

    # Show engine info
    lines = [
        f"[dim]TTS engine :[/dim]  [jarvis]{speaker.engine_name}[/jarvis]",
        f"[dim]LLM model  :[/dim]  [jarvis]{config.get('ollama', {}).get('model', 'llama3')}[/jarvis]",
        f"[dim]Wake word  :[/dim]  [jarvis]{config.get('jarvis', {}).get('wake_word', 'jarvis')}[/jarvis]",
        f"[dim]Memory     :[/dim]  [jarvis]SQLite — active[/jarvis]",
    ]
    for line in lines:
        console.print(f"  {line}")

    console.print()
    console.rule("[dim]Systems online[/dim]", style="cyan")
    console.print("[info]  Type your message and press Enter.[/info]")
    console.print("[info]  Type [bold]![/bold] to activate voice input.[/info]")
    console.print("[info]  Type [bold]brief[/bold] for a full status briefing.[/info]")
    console.print("[info]  Type [bold]exit[/bold] to shut down.[/info]")
    console.print()

    greeting = f"Good day, {user_name}. All systems are online and ready."
    console.print(f"[jarvis]J.A.R.V.I.S.:[/jarvis] {greeting}\n")
    speaker.speak(greeting, blocking=False)


# ------------------------------------------------------------------
# Reminder watcher (background thread)
# ------------------------------------------------------------------

def _watch_reminders(speaker: Speaker, console: Console) -> None:
    """Background thread: watch for fired reminders and announce them."""
    while True:
        try:
            msg = reminder_module.fired_queue.get(timeout=1)
            console.print(f"\n[warn]⚡ {msg}[/warn]")
            speaker.speak(msg, blocking=False)
        except Exception:
            pass  # Empty queue or shutdown — keep looping


# ------------------------------------------------------------------
# Conversation turns
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

    console.print("\n[jarvis]J.A.R.V.I.S.:[/jarvis] ", end="")
    tokens: list[str] = []

    def _on_token(token: str) -> None:
        tokens.append(token)
        console.print(token, end="", markup=False, highlight=False)

    response = brain.process(user_text, stream_callback=_on_token)

    streamed = "".join(tokens).strip()
    if response != streamed:
        # Tool was dispatched — replace streamed output with tool result
        console.print(f"\r[jarvis]J.A.R.V.I.S.:[/jarvis] {response}           ")
    else:
        console.print()  # newline after stream

    memory.add_message("assistant", response)
    speaker.speak(response, blocking=False)


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
        console.print(
            "[info]Grant microphone access: "
            "System Settings → Privacy & Security → Microphone[/info]"
        )


# ------------------------------------------------------------------
# Main loop
# ------------------------------------------------------------------

def main() -> None:
    config = load_config()

    speaker = Speaker(config)
    memory = ConversationMemory(config)
    brain = Brain(config, memory)

    if not check_ollama(brain):
        console.print(
            "[error]Ollama is not running.[/error]\n"
            "[info]  Start it with: ollama serve[/info]\n"
            "[info]  Pull a model:  ollama pull llama3[/info]"
        )
        sys.exit(1)

    boot_sequence(config, speaker)

    # Start reminder watcher thread
    threading.Thread(
        target=_watch_reminders,
        args=(speaker, console),
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
            if user_input == "!":
                voice_turn(config, brain, speaker, memory)
            else:
                run_turn(user_input, brain, speaker, memory)

    except KeyboardInterrupt:
        reminder_module.cancel_all()
        console.print("\n[info]Shutting down all systems. Goodbye, sir.[/info]")
        speaker.speak("Shutting down. Goodbye, sir.")
        memory.close()


if __name__ == "__main__":
    main()
