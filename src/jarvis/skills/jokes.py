"""Joke skill — fetches a random joke from the Official Joke API (no key)."""

try:
    import requests as _requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False


def get_joke() -> str:
    """Return a random spoken joke."""
    if not _HAS_REQUESTS:
        return (
            "I would tell you a joke about humour modules, sir, "
            "but I can't access the requests library."
        )

    try:
        resp = _requests.get(
            "https://official-joke-api.appspot.com/random_joke",
            timeout=6,
            headers={"User-Agent": "Jarvis-Assistant/1.0"},
        )
        resp.raise_for_status()
        data = resp.json()

        setup     = data.get("setup", "").strip()
        punchline = data.get("punchline", "").strip()

        if setup and punchline:
            return f"{setup} … {punchline}"
        return "I seem to have misplaced my sense of humour, sir."

    except Exception:
        return "The humour module appears to be offline, sir."
