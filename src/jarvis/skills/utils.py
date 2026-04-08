"""Built-in utility skills: time, date, notes, calculator."""

import math
import os
from datetime import datetime
from pathlib import Path


# ---------------------------------------------------------------------------
# Time / Date
# ---------------------------------------------------------------------------

def get_time() -> str:
    return datetime.now().strftime("The time is %I:%M %p.")


def get_date() -> str:
    return datetime.now().strftime("Today is %A, %B %d, %Y.")


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------

_NOTES_FILE = Path(os.path.expanduser("~/.jarvis/notes.txt"))


def _ensure_notes_file() -> None:
    _NOTES_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not _NOTES_FILE.exists():
        _NOTES_FILE.touch()


def add_note(text: str) -> str:
    _ensure_notes_file()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(_NOTES_FILE, "a") as f:
        f.write(f"[{timestamp}] {text}\n")
    return f"Note saved: {text}"


def read_notes(limit: int = 5) -> str:
    _ensure_notes_file()
    lines = _NOTES_FILE.read_text().strip().splitlines()
    if not lines:
        return "You have no notes."
    recent = lines[-limit:]
    return "Your recent notes: " + ". ".join(ln.split("] ", 1)[-1] for ln in recent) + "."


# ---------------------------------------------------------------------------
# Calculator
# ---------------------------------------------------------------------------

_SAFE_NAMES = {k: v for k, v in math.__dict__.items() if not k.startswith("_")}
_SAFE_NAMES.update({"abs": abs, "round": round, "int": int, "float": float})


def calculate(expr: str) -> str:
    try:
        # Strip anything that isn't a safe math expression
        safe_expr = "".join(c for c in expr if c in "0123456789+-*/.() eE,^")
        safe_expr = safe_expr.replace("^", "**")
        result = eval(safe_expr, {"__builtins__": {}}, _SAFE_NAMES)  # noqa: S307
        return f"The answer is {result}."
    except Exception:
        return "I couldn't calculate that."
