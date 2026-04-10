"""Clipboard skill — read and write the system clipboard."""

import platform
import subprocess


def read_clipboard() -> str:
    """Return current clipboard contents as a spoken string."""
    text = _get()
    if text is None:
        return "Clipboard access is unavailable on this system, sir."
    text = text.strip()
    if not text:
        return "The clipboard is empty, sir."
    preview = text[:400]
    suffix = f" … ({len(text)} characters total)" if len(text) > 400 else ""
    return f"Clipboard contains: {preview}{suffix}"


def write_clipboard(text: str) -> str:
    """Write *text* to the clipboard."""
    ok = _set(text)
    if not ok:
        return "Clipboard write is unavailable on this system, sir."
    preview = text[:60] + ("…" if len(text) > 60 else "")
    return f"Copied to clipboard: {preview}"


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _get() -> str | None:
    try:
        if platform.system() == "Darwin":
            r = subprocess.run(["pbpaste"], capture_output=True, text=True)
            return r.stdout
        # Linux: try xclip then xsel
        for cmd in (
            ["xclip", "-selection", "clipboard", "-o"],
            ["xsel", "--clipboard", "--output"],
        ):
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
                if r.returncode == 0:
                    return r.stdout
            except FileNotFoundError:
                continue
        return None
    except Exception:
        return None


def _set(text: str) -> bool:
    try:
        encoded = text.encode()
        if platform.system() == "Darwin":
            subprocess.run(["pbcopy"], input=encoded, check=True)
            return True
        for cmd in (
            ["xclip", "-selection", "clipboard"],
            ["xsel", "--clipboard", "--input"],
        ):
            try:
                subprocess.run(cmd, input=encoded, check=True, timeout=3)
                return True
            except FileNotFoundError:
                continue
        return False
    except Exception:
        return False
