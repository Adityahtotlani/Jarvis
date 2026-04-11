"""Reminder skill — thread-based timers that fire into a queue."""

import queue
import re
import threading
import time
from datetime import datetime, timedelta

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
# Parsing helpers (used by brain.py)
# ---------------------------------------------------------------------------

def _parse_time_expr(expr: str) -> datetime | None:
    """
    Parse a time expression (e.g., "3pm", "15:30", "9:00am") into a time object.
    Returns datetime.time or None if unparseable.
    """
    expr = expr.strip().lower()

    # Handle 12-hour format: "3pm", "3:30pm", "9am", "9:30am"
    m = re.match(r"^(\d{1,2}):?(\d{2})?\s*(am|pm)$", expr)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2)) if m.group(2) else 0
        period = m.group(3)

        if period == "pm" and hour != 12:
            hour += 12
        elif period == "am" and hour == 12:
            hour = 0

        return datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)

    # Handle 24-hour format: "15:30", "9:00"
    m = re.match(r"^(\d{1,2}):(\d{2})$", expr)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2))
        return datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)

    return None


def _parse_relative_time(expr: str) -> float | None:
    """
    Parse relative time expressions like "in 2 hours", "in 30 minutes", etc.
    Returns minutes from now, or None if unparseable.
    """
    expr = expr.strip().lower()

    # "in X hours"
    m = re.match(r"^in\s+(\d+(?:\.\d+)?)\s*hours?$", expr)
    if m:
        return float(m.group(1)) * 60

    # "in X minutes"
    m = re.match(r"^in\s+(\d+(?:\.\d+)?)\s*(?:minutes?|mins?)?$", expr)
    if m:
        return float(m.group(1))

    return None


def _calculate_minutes_until(target: datetime) -> float:
    """Calculate minutes from now until target datetime. If target is in the past, add a day."""
    now = datetime.now()
    delta = target - now

    # If target is in the past, assume it's tomorrow
    if delta.total_seconds() < 0:
        target = target + timedelta(days=1)
        delta = target - now

    return delta.total_seconds() / 60


def parse_remind_arg(arg: str) -> tuple[str, float]:
    """
    Parse '[REMIND: message ...]' argument into (message, minutes).
    Supports multiple formats:
      Relative:
        - "buy milk in 15"
        - "take medication in 5 minutes"
        - "call John in 2 hours"
      Absolute:
        - "buy milk at 3pm"
        - "call John at 3:30pm"
        - "check email tomorrow at 9am"
      Legacy:
        - "check the oven in 0.5"
    Returns (message, minutes). Defaults to 5 minutes if unparseable.
    """
    arg = arg.strip()

    # Try "... at <time>" pattern (absolute time)
    # Matches: "message at 3pm", "message at 15:30", "message at 3:30pm"
    m = re.match(r"^(.+?)\s+at\s+(\d{1,2}):?(\d{2})?\s*(am|pm)?$", arg, re.IGNORECASE)
    if m:
        message = m.group(1).strip()
        time_expr = arg[arg.rfind(" at ") + 4:].strip()
        target = _parse_time_expr(time_expr)
        if target:
            minutes = _calculate_minutes_until(target)
            return message, minutes

    # Try "... tomorrow at <time>" pattern
    m = re.match(r"^(.+?)\s+tomorrow\s+at\s+(\d{1,2}):?(\d{2})?\s*(am|pm)?$", arg, re.IGNORECASE)
    if m:
        message = m.group(1).strip()
        time_expr = arg[arg.rfind(" at ") + 4:].strip()
        target = _parse_time_expr(time_expr)
        if target:
            target = target + timedelta(days=1)
            minutes = _calculate_minutes_until(target)
            return message, minutes

    # Try "... in <N> [minutes|hours]" pattern (relative time)
    m = re.match(
        r"^(.+?)\s+in\s+(\d+(?:\.\d+)?)\s*(?:hours?|minutes?|mins?|m)?$",
        arg,
        re.IGNORECASE,
    )
    if m:
        message = m.group(1).strip()
        relative = f"in {m.group(2)}"
        # Detect hours vs minutes
        if "hour" in arg.lower():
            minutes = float(m.group(2)) * 60
        else:
            minutes = float(m.group(2))
        return message, minutes

    # Fallback: extract last number
    nums = re.findall(r"\d+(?:\.\d+)?", arg)
    if nums:
        minutes = float(nums[-1])
        idx = arg.rfind(nums[-1])
        msg = arg[:idx].rstrip().rstrip("in").rstrip()
        return msg or arg, minutes

    return arg, 5.0
