"""Jarvis — entry point.

Modes
-----
- Default: type commands in the terminal
- Voice:   type  !  and press Enter to speak one command
"""

import os
import sys

import yaml
from rich.console import Console
from rich.text import Text
from rich.theme import Theme

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from jarvis.core.brain import Brain
from jarvis.core.speaker import Speaker
from jarvis.memory.conversation import ConversationMemory

# ----- readline history (best-effort; not available everywhere) --------
try:
    import readline
    _HISTORY_FILE = os.path.expanduser("~/.jarvis_history")
    try:
        readline.read_history_file(_HISTORY_FILE)
    except FileNotFoundError:
        pass
    import atexit
    atexit.register(readline.write_history_file, _HISTORY_FILE)
except ImportError:
    pass

# ----- Rich console ----------------------------------------------------
_THEME = Theme({
    "jarvis": "bold cyan",
    "you":    "bold green",
    "info":   "dim white",
    "error":  "bold red",
    "prompt": "bold yellow",
})
console = Console(theme=_THEME)


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


def run_turn(
    user_text: str,
    brain: Brain,
    speaker: Speaker,
    memory: ConversationMemory,
) -> None:
    if not user_text.strip():
        return

    memory.add_message("user", user_text)

    # Stream the LLM response token by token
    console.print("\n[jarvis]Jarvis:[/jarvis] ", end="")
    tokens: list[str] = []

    def _on_token(token: str) -> None:
        tokens.append(token)
        console.print(token, end="", markup=False, highlight=False)

    response = brain.process(user_text, stream_callback=_on_token)

    # If brain dispatched a tool, the tool result replaces the streamed text
    streamed = "".join(tokens).strip()
    if response != streamed:
        # Tool was called — print the actual result (replace streamed tag)
        console.print(f"\r[jarvis]Jarvis:[/jarvis] {response}           ")
    else:
        console.print()  # newline after streamed text

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
        speaker.speak("Yes?", blocking=False)
        user_text = listener.transcribe_command()
        if user_text.strip():
            console.print(f"[you]You (voice):[/you] {user_text}")
            run_turn(user_text, brain, speaker, memory)
        else:
            console.print("[info]Didn't catch that.[/info]")
    except Exception as e:
        console.print(f"[error]Voice error:[/error] {e}")
        console.print("[info]Grant mic access: System Settings → Privacy & Security → Microphone[/info]")


def main() -> None:
    config = load_config()

    speaker  = Speaker(config)
    memory   = ConversationMemory(config)
    brain    = Brain(config, memory)

    if not check_ollama(brain):
        console.print(
            "[error]Ollama is not running.[/error]\n"
            "[info]  ollama serve[/info]\n"
            "[info]  ollama pull llama3[/info]"
        )
        sys.exit(1)

    console.rule("[jarvis]J A R V I S[/jarvis]")
    console.print("[info]Type your message and press Enter.[/info]")
    console.print("[info]Type [bold]![/bold] to activate voice input.[/info]")
    console.print("[info]Type [bold]exit[/bold] to quit.[/info]\n")
    speaker.speak("Jarvis online.")

    try:
        while True:
            try:
                console.print("[you]You:[/you] ", end="")
                user_input = input().strip()
            except EOFError:
                break

            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "bye"):
                raise KeyboardInterrupt
            if user_input == "!":
                voice_turn(config, brain, speaker, memory)
            else:
                run_turn(user_input, brain, speaker, memory)

    except KeyboardInterrupt:
        console.print("\n[info]Shutting down.[/info]")
        speaker.speak("Goodbye.")
        memory.close()


if __name__ == "__main__":
    main()
