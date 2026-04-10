"""Vision skill — screen analysis via Ollama LLaVA multimodal model.

Setup:
    ollama pull llava       # ~4.7 GB
    # or a smaller variant: ollama pull llava:7b
"""

import base64
import os
import platform
import subprocess
import tempfile


def analyze_screen(question: str = "") -> str:
    """
    Capture the current screen and describe what's visible using LLaVA.
    If *question* is provided, answer it about the screen contents.
    """
    try:
        import ollama
    except ImportError:
        return "Vision analysis requires the ollama library, sir."

    # 1. Take screenshot
    tmp = tempfile.mktemp(suffix=".png")
    try:
        _capture(tmp)
    except Exception as e:
        return f"I couldn't capture the screen: {e}"

    if not os.path.exists(tmp) or os.path.getsize(tmp) == 0:
        return "Screen capture failed, sir. Check screen recording permissions."

    try:
        # 2. Base64 encode for Ollama
        with open(tmp, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()

        # 3. Build prompt
        if question.strip():
            prompt = (
                f"Look at this screenshot and answer: {question}\n\n"
                "Respond in 2-3 sentences as J.A.R.V.I.S., addressing the user as sir. "
                "No markdown or lists."
            )
        else:
            prompt = (
                "Describe what's visible on this screen. "
                "Respond in 2-3 sentences as J.A.R.V.I.S., addressing the user as sir. "
                "No markdown or lists."
            )

        # 4. Query LLaVA via Ollama
        client = ollama.Client(host="http://localhost:11434")
        response = client.generate(
            model="llava",
            prompt=prompt,
            images=[img_b64],
            stream=False,
            options={"temperature": 0.4},
        )
        text = response.get("response", "").strip()
        return text or "I was unable to interpret the screen contents, sir."

    except ollama.ResponseError as e:
        if "not found" in str(e).lower():
            return (
                "Vision requires the llava model, sir. "
                "Please run: ollama pull llava"
            )
        return f"Vision error: {e}"
    except Exception as e:
        return f"Vision analysis failed: {str(e)[:120]}"
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _capture(path: str) -> None:
    """Capture screen to *path*. Raises on failure."""
    system = platform.system()
    if system == "Darwin":
        subprocess.run(["screencapture", "-x", path], check=True, timeout=10)
        return

    # Linux — try multiple tools
    for cmd in (
        ["scrot",            path],
        ["gnome-screenshot", "-f", path],
        ["maim",             path],
        ["import",           "-window", "root", path],
    ):
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=10)
            return
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue

    raise RuntimeError("No screenshot tool found (scrot, gnome-screenshot, maim)")
