"""Jarvis — entry point.

Activation paths
----------------
1. Wake word: say "Jarvis" into the mic → Jarvis responds "Yes?"
2. Hotkey:    press Cmd+Shift+J         → same behaviour, no wake word needed
"""

import os
import sys
import threading
import time

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
        os.path.dirname(__file__), "..", "..", "..", "config", "settings.yaml"
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


def main() -> None:
    config = load_config()

    speaker = Speaker(config)
    memory = ConversationMemory(config)
    listener = Listener(config)
    brain = Brain(config, memory)

    # --- Check Ollama is reachable ----------------------------------------
    if not check_ollama(brain):
        print(
            "[Jarvis] ERROR: Ollama is not running.\n"
            "  Start it with:  ollama serve\n"
            "  Then pull the model:  ollama pull llama3"
        )
        sys.exit(1)

    # --- Hotkey trigger event ----------------------------------------------
    hotkey_event = threading.Event()
    hotkey_listener = HotkeyListener(config, hotkey_event)
    hotkey_listener.start()

    hotkey_combo = config.get("jarvis", {}).get("hotkey", "<cmd>+<shift>+j")
    print(f"[Jarvis] Online. Hotkey: {hotkey_combo}")
    speaker.speak("Jarvis online. How can I assist you?")

    # --- Main loop ---------------------------------------------------------
    try:
        while True:
            # Wait for activation via wake word OR hotkey
            activated_by_hotkey = False

            # Poll for hotkey (non-blocking) while also listening for wake word
            # Run wake-word listener in a thread so hotkey can interrupt
            wake_detected = threading.Event()

            def _wake_watcher():
                listener.wait_for_wake_word()
                wake_detected.set()

            wake_thread = threading.Thread(target=_wake_watcher, daemon=True)
            wake_thread.start()

            while not wake_detected.is_set() and not hotkey_event.is_set():
                time.sleep(0.05)

            if hotkey_event.is_set():
                hotkey_event.clear()
                activated_by_hotkey = True
            # If both fired, that's fine — proceed

            speaker.speak("Yes?", blocking=False)
            user_text = listener.transcribe_command()

            if not user_text.strip():
                continue

            print(f"[You] {user_text}")
            memory.add_message("user", user_text)

            response = brain.process(user_text)
            print(f"[Jarvis] {response}")
            memory.add_message("assistant", response)

            speaker.speak(response)

    except KeyboardInterrupt:
        print("\n[Jarvis] Shutting down.")
        speaker.speak("Goodbye.")
        hotkey_listener.stop()
        memory.close()


if __name__ == "__main__":
    main()
