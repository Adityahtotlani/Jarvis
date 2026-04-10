"""Timer skill — countdown timers separate from reminders.

Unlike reminders (which hold a message), timers are anonymous countdowns
with a progress-aware display in the web dashboard.
"""

import re
import threading
import time

# Module-level state
_timers: list[dict] = []
_lock = threading.Lock()
_counter = 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def start(arg: str) -> str:
    """Parse *arg* (e.g. '5 minutes') and start a countdown timer."""
    global _counter

    seconds = _parse_duration(arg)
    if seconds is None:
        return (
            "I need a duration, sir. "
            "For example: 'timer 5 minutes' or 'set a 30-second timer'."
        )

    if seconds < 1:
        return "The timer duration must be at least one second, sir."

    with _lock:
        _counter += 1
        tid = _counter

    def _fire() -> None:
        with _lock:
            _timers[:] = [t for t in _timers if t["id"] != tid]
        # Defer import to avoid circular dependency
        from jarvis.skills.reminders import fired_queue
        fired_queue.put(f"Timer complete, sir.")

    t = threading.Timer(seconds, _fire)
    t.daemon = True
    t.start()

    with _lock:
        _timers.append({
            "id":        tid,
            "duration":  seconds,
            "start":     time.time(),
            "end":       time.time() + seconds,
            "timer":     t,
        })

    return f"Timer set for {_humanize(seconds)}, sir."


def list_active() -> str:
    """Spoken list of active timers."""
    with _lock:
        active = list(_timers)

    if not active:
        return "You have no active timers, sir."

    now = time.time()
    parts = []
    for t in active:
        remaining = max(0, t["end"] - now)
        parts.append(_humanize(remaining))

    if len(parts) == 1:
        return f"Your timer has {parts[0]} remaining, sir."
    return f"You have {len(parts)} timers running: " + "; ".join(parts) + "."


def cancel_all() -> str:
    """Cancel every active timer."""
    with _lock:
        count = len(_timers)
        for t in _timers:
            try:
                t["timer"].cancel()
            except Exception:
                pass
        _timers.clear()
    if count == 0:
        return "There were no active timers, sir."
    return f"Cancelled {count} timer{'s' if count != 1 else ''}, sir."


def get_active_timers() -> list[dict]:
    """Return a serialisable list of active timers for the web UI."""
    with _lock:
        now = time.time()
        return [
            {
                "id":        t["id"],
                "duration":  t["duration"],
                "end":       t["end"],
                "remaining": max(0, t["end"] - now),
            }
            for t in _timers
        ]


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_duration(arg: str) -> float | None:
    """Parse natural language duration into seconds."""
    arg = arg.strip().lower()
    if not arg:
        return None

    # Strip common filler
    arg = re.sub(r"\b(for|of|a|an|set|start)\b", " ", arg).strip()

    total = 0.0
    found = False

    # Match patterns like "1 hour 30 minutes 10 seconds"
    for match in re.finditer(
        r"(\d+(?:\.\d+)?)\s*(hours?|hrs?|h|minutes?|mins?|m|seconds?|secs?|s)\b",
        arg,
    ):
        value = float(match.group(1))
        unit  = match.group(2)
        if   unit.startswith("h"):              total += value * 3600
        elif unit.startswith("m") and "in" in unit: total += value * 60
        elif unit == "m":                       total += value * 60
        elif unit.startswith("s"):              total += value
        found = True

    if found:
        return total

    # Single number — assume minutes
    m = re.match(r"^(\d+(?:\.\d+)?)$", arg)
    if m:
        return float(m.group(1)) * 60

    return None


def _humanize(seconds: float) -> str:
    """Format seconds as 'Xh Ym Zs' for speech."""
    seconds = int(round(seconds))
    if seconds < 60:
        return f"{seconds} second{'s' if seconds != 1 else ''}"
    if seconds < 3600:
        mins = seconds // 60
        secs = seconds % 60
        if secs == 0:
            return f"{mins} minute{'s' if mins != 1 else ''}"
        return f"{mins} minute{'s' if mins != 1 else ''} and {secs} second{'s' if secs != 1 else ''}"
    hrs  = seconds // 3600
    mins = (seconds % 3600) // 60
    if mins == 0:
        return f"{hrs} hour{'s' if hrs != 1 else ''}"
    return f"{hrs} hour{'s' if hrs != 1 else ''} and {mins} minute{'s' if mins != 1 else ''}"
