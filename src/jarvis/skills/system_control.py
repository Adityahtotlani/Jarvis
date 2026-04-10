"""System control skill — open apps, run safe commands, adjust volume on macOS."""

import platform
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
    Blocks shell operators and dangerous constructs.
    """
    blocked = [";", "&&", "||", "|", ">", "<", "`", "$", "\n", "$(", "${"]
    for tok in blocked:
        if tok in cmd:
            return "I can't run that command — it looks unsafe."

    try:
        args = shlex.split(cmd)
    except ValueError:
        return "I couldn't parse that command."

    if not args:
        return "Empty command."

    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=15,
    )
    output = (result.stdout or result.stderr or "Done.").strip()
    if len(output) > 500:
        return output[:500] + "… (truncated)"
    return output or "Done."


def lock_screen() -> str:
    """Lock the workstation."""
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.run(
                ["/System/Library/CoreServices/Menu Extras/User.menu/Contents/Resources/CGSession", "-suspend"],
                check=False,
            )
        elif system == "Linux":
            for cmd in (["loginctl", "lock-session"], ["xdg-screensaver", "lock"]):
                if subprocess.run(cmd, check=False).returncode == 0:
                    break
        else:
            return "Screen locking is not supported on this platform, sir."
        return "Locking the screen, sir."
    except Exception:
        return "I couldn't lock the screen, sir."


def sleep_computer() -> str:
    """Put the computer to sleep."""
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.run(["pmset", "sleepnow"], check=False)
        elif system == "Linux":
            subprocess.run(["systemctl", "suspend"], check=False)
        else:
            return "Sleep is not supported on this platform, sir."
        return "Going to sleep, sir."
    except Exception:
        return "I couldn't put the computer to sleep, sir."
