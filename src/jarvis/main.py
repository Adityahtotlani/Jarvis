"""Jarvis — entry point.

Modes
-----
- Default: type commands in the terminal (no mic needed)
- Voice:   press Cmd+Shift+J to speak one command, then returns to text mode
"""

import os
import sys
import threading

import yaml

# Allow running as `python src/jarvis/main.py` without installing the package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from jarvis.core.brain import Brain
from jarvis.core.hotkey import HotkeyListener
from jarvis.core.listener import Listener
from jarvis.core.speaker import Speaker
from jarvis.memory.conversation import ConversationMemory


def load_config() -> dict:
    config_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "config", "settings.yaml"
    )
    config_path = os.path.normpath(config_path)
    with open(config_path) as f:
        return yaml.safe_load(f)


def check_ollama(brain: Brain) -> bool:
    try:
        import ollama
        client = ollama.Client(host=brain.host)
        client.list()
        return True
    except Exception:
        return False


def process(user_text: str, brain: Brain, speaker: Speaker, memory: ConversationMemory) -> None:
    """Run a single turn: think → speak → remember."""
    if not user_text.strip():
        return
    print(f"[You] {user_text}")
    memory.add_message("user", user_text)
    response = brain.process(user_text)
    print(f"[Jarvis] {response}")
    memory.add_message("assistant", response)
    speaker.speak(response)


def main() -> None:
    config = load_config()
    hotkey_combo = config.get("jarvis", {}).get("hotkey", "<cmd>+<shift>+j")

    speaker = Speaker(config)
    memory = ConversationMemory(config)
    brain = Brain(config, memory)

    # --- Check Ollama is reachable -------------------------------------------
    if not check_ollama(brain):
        print(
            "[Jarvis] ERROR: Ollama is not running.\n"
            "  Start it with:  ollama serve\n"
            "  Then pull the model:  ollama pull llama3"
        )
        sys.exit(1)

    # --- Hotkey → voice mode trigger -----------------------------------------
    voice_event = threading.Event()
    hotkey_listener = HotkeyListener(config, voice_event)
    hotkey_listener.start()

    print(f"[Jarvis] Online. Type your commands below.")
    print(f"[Jarvis] Press {hotkey_combo} at any time to speak instead.\n")
    speaker.speak("Jarvis online. How can I assist you?")

    # --- Main loop -----------------------------------------------------------
    try:
        while True:
            # Non-blocking check for hotkey before showing the prompt
            if voice_event.is_set():
                voice_event.clear()
                _handle_voice(config, brain, speaker, memory)
                continue

            try:
                user_text = input("You: ").strip()
            except EOFError:
                break

            if not user_text:
                continue

            if user_text.lower() in ("exit", "quit", "bye"):
                raise KeyboardInterrupt

            process(user_text, brain, speaker, memory)

    except KeyboardInterrupt:
        print("\n[Jarvis] Shutting down.")
        speaker.speak("Goodbye.")
        hotkey_listener.stop()
        memory.close()


def _handle_voice(config: dict, brain: Brain, speaker: Speaker, memory: ConversationMemory) -> None:
    """One round of voice input."""
    try:
        from jarvis.core.listener import Listener
        listener = Listener(config)
        print("[Jarvis] Listening... (speak now)")
        speaker.speak("Yes?", blocking=False)
        user_text = listener.transcribe_command()
        if user_text.strip():
            process(user_text, brain, speaker, memory)
        else:
            print("[Jarvis] Didn't catch that.")
    except Exception as e:
        print(f"[Jarvis] Voice error: {e}. Try granting mic access in System Settings.")


if __name__ == "__main__":
    main()
