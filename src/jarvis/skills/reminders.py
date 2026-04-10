"""Reminder skill — thread-based timers that fire into a queue."""

import queue
import re
import threading
import time
from datetime import datetime

# Fired reminders land here; main.py watches this queue.
fired_queue: queue.Queue = queue.Queue()

_reminders: list[dict] = []
_lock = threading.Lock()
_counter = 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def set_reminder(message: str, minutes: float) -> str:
    """
    Schedule *message* to fire after *minutes* minutes.
    Returns a confirmation string.
    """
    global _counter
    with _lock:
        _counter += 1
        rid = _counter

    def _fire() -> None:
        with _lock:
            _reminders[:] = [r for r in _reminders if r["id"] != rid]
        fired_queue.put(f"Reminder, sir: {message}")

    timer = threading.Timer(minutes * 60, _fire)
    timer.daemon = True
    timer.start()

    fire_at = time.time() + minutes * 60
    with _lock:
        _reminders.append({
            "id": rid,
            "message": message,
            "fire_at": fire_at,
            "timer": timer,
        })

    mins_int = int(minutes)
    label = f"{mins_int} minute{'s' if mins_int != 1 else ''}"
    return f"Reminder set. I'll alert you in {label}: {message}."


def list_reminders() -> str:
    """Return spoken list of active reminders."""
    with _lock:
        active = list(_reminders)

    if not active:
        return "You have no active reminders, sir."

    now = time.time()
    parts = []
    for r in active:
        remaining = max(0.0, (r["fire_at"] - now) / 60)
        parts.append(f"{r['message']} in {remaining:.0f} minutes")

    return "Active reminders: " + "; ".join(parts) + "."


def cancel_all() -> None:
    """Cancel all pending reminders (e.g., on shutdown)."""
    with _lock:
        for r in _reminders:
            try:
                r["timer"].cancel()
            except Exception:
                pass
        _reminders.clear()


# ---------------------------------------------------------------------------
# Parsing helper (used by brain.py)
# ---------------------------------------------------------------------------

def parse_remind_arg(arg: str) -> tuple[str, float]:
    """
    Parse '[REMIND: buy milk in 10]' argument into (message, minutes).
    Accepts formats like:
      "call John in 15"
      "take medication in 5 minutes"
      "check the oven in 0.5"
    Returns (message, minutes). Defaults to 5 minutes if unparseable.
    """
    # Pattern: everything before " in <N> [minutes|mins|m]"
    m = re.search(
        r"^(.+?)\s+in\s+(\d+(?:\.\d+)?)\s*(?:minutes?|mins?|m)?$",
        arg.strip(),
        re.IGNORECASE,
    )
    if m:
        return m.group(1).strip(), float(m.group(2))

    # Fallback: extract last number
    nums = re.findall(r"\d+(?:\.\d+)?", arg)
    if nums:
        minutes = float(nums[-1])
        idx = arg.rfind(nums[-1])
        msg = arg[:idx].rstrip().rstrip("in").rstrip()
        return msg or arg, minutes

    return arg, 5.0
