"""System control skill — open apps, run safe commands, adjust volume on macOS."""

import shlex
import subprocess


def open_app(name: str) -> str:
    """Open a macOS application by name."""
    result = subprocess.run(
        ["open", "-a", name],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return f"Opening {name}."
    return f"I couldn't open {name}. Make sure the app is installed."


def open_url(url: str) -> str:
    """Open a URL in the default browser."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    subprocess.run(["open", url], check=False)
    return f"Opening {url}."


def set_volume(level: int) -> str:
    """Set system volume to *level* (0–100) via AppleScript."""
    level = max(0, min(100, level))
    script = f"set volume output volume {level}"
    subprocess.run(["osascript", "-e", script], check=False)
    return f"Volume set to {level} percent."


def run_command(cmd: str) -> str:
    """
    Run a safe shell command and return its stdout (first 500 chars).
    Blocks shell operators to prevent injection.
    """
    blocked = [";", "&&", "||", "|", ">", "<", "`", "$"]
    for tok in blocked:
        if tok in cmd:
            return "I can't run that command — it looks unsafe."

    try:
        args = shlex.split(cmd)
    except ValueError:
        return "I couldn't parse that command."

    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=15,
    )
    output = (result.stdout or result.stderr or "Done.").strip()
    return output[:500]
