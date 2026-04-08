"""Jarvis — entry point.

Modes
-----
- Default: type commands in the terminal
- Voice:   type  !  and press Enter to speak one command
"""

import os
import sys

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from jarvis.core.brain import Brain
from jarvis.core.speaker import Speaker
from jarvis.memory.conversation import ConversationMemory


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


def run_turn(user_text: str, brain: Brain, speaker: Speaker, memory: ConversationMemory) -> None:
    if not user_text.strip():
        return
    print(f"[You] {user_text}")
    memory.add_message("user", user_text)
    response = brain.process(user_text)
    print(f"[Jarvis] {response}")
    memory.add_message("assistant", response)
    speaker.speak(response)


def voice_turn(config: dict, brain: Brain, speaker: Speaker, memory: ConversationMemory) -> None:
    try:
        from jarvis.core.listener import Listener
        listener = Listener(config)
        print("[Jarvis] Listening… speak now.")
        speaker.speak("Yes?", blocking=False)
        user_text = listener.transcribe_command()
        if user_text.strip():
            run_turn(user_text, brain, speaker, memory)
        else:
            print("[Jarvis] Didn't catch that.")
    except Exception as e:
        print(f"[Jarvis] Voice error: {e}")
        print("  → Grant mic access: System Settings → Privacy & Security → Microphone")


def main() -> None:
    config = load_config()

    speaker = Speaker(config)
    memory = ConversationMemory(config)
    brain = Brain(config, memory)

    if not check_ollama(brain):
        print(
            "[Jarvis] ERROR: Ollama is not running.\n"
            "  ollama serve   (then in another tab:  ollama pull llama3)"
        )
        sys.exit(1)

    print("[Jarvis] Online. Type your message and press Enter.")
    print("[Jarvis] Type  !  to activate voice input.\n")
    speaker.speak("Jarvis online.")

    try:
        while True:
            try:
                user_input = input("You: ").strip()
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
        print("\n[Jarvis] Shutting down.")
        speaker.speak("Goodbye.")
        memory.close()


if __name__ == "__main__":
    main()
