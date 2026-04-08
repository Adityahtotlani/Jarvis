import sys
import os
from unittest.mock import MagicMock

# Add src/ to import path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

# Stub audio/whisper/pynput libraries not available in CI (Linux, no PortAudio/GPU)
for _mod in ("sounddevice", "whisper", "pynput", "pynput.keyboard"):
    sys.modules.setdefault(_mod, MagicMock())
