"""Weather skill using wttr.in — no API key required."""

import re

try:
    import requests as _requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False


def get_weather(location: str = "") -> str:
    """
    Fetch current weather for *location* (or local if blank).
    Uses wttr.in which requires no API key.
    Returns a plain-English string suitable for TTS.
    """
    if not _HAS_REQUESTS:
        return "Weather lookup is unavailable — the requests library is not installed, sir."

    loc = location.strip().replace(" ", "+")
    url = f"https://wttr.in/{loc}?format=3"

    try:
        resp = _requests.get(
            url,
            timeout=8,
            headers={"User-Agent": "Jarvis-Assistant/1.0"},
        )
        resp.raise_for_status()
        raw = resp.text.strip()
        spoken = _clean_for_tts(raw)
        if spoken:
            return f"Current conditions: {spoken}."
        return "I was unable to parse the weather data, sir."
    except _requests.exceptions.Timeout:
        return "The weather service is not responding. Try again in a moment, sir."
    except Exception:
        return "I couldn't retrieve weather information at this time, sir."


def _clean_for_tts(text: str) -> str:
    """Strip emoji and special characters, expand abbreviations for TTS."""
    # Remove emoji / non-ASCII
    text = re.sub(r"[^\x00-\x7F]+", "", text).strip()
    # Normalise multiple spaces
    text = re.sub(r"\s{2,}", " ", text)
    # Replace degree symbol variants
    text = text.replace("\u00b0", " degrees ")
    # Remove leftover symbols
    text = re.sub(r"[+]{1}(\d)", r"\1", text)  # +15 → 15
    return text.strip()
