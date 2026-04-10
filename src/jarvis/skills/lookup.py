"""Lookup skills — Wikipedia facts and text translation (no API key required)."""

try:
    import requests as _requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

# ---------------------------------------------------------------------------
# Wikipedia
# ---------------------------------------------------------------------------

def wikipedia(query: str) -> str:
    """
    Fetch a spoken summary of the Wikipedia article best matching *query*.
    Uses the Wikipedia REST API — no key required.
    """
    if not _HAS_REQUESTS:
        return "Wikipedia lookup requires the requests library, sir."

    query = query.strip()
    if not query:
        return "Please specify what you'd like me to look up, sir."

    try:
        # 1. Search for the best-matching article title
        search = _requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action":  "query",
                "list":    "search",
                "srsearch": query,
                "format":  "json",
                "srlimit": 1,
            },
            timeout=8,
            headers={"User-Agent": "Jarvis-Assistant/1.0"},
        )
        search.raise_for_status()
        results = search.json()["query"]["search"]

        if not results:
            return f"I couldn't find a Wikipedia article on that, sir."

        title = results[0]["title"]

        # 2. Fetch the article summary
        summary = _requests.get(
            f"https://en.wikipedia.org/api/rest_v1/page/summary/{title.replace(' ', '_')}",
            timeout=8,
            headers={"User-Agent": "Jarvis-Assistant/1.0"},
        )
        summary.raise_for_status()
        data    = summary.json()
        extract = data.get("extract", "").strip()

        if not extract:
            return f"I found the article '{title}' but it has no summary, sir."

        # Limit to ~3 spoken sentences
        sentences = extract.split(". ")
        spoken    = ". ".join(sentences[:3])
        if not spoken.endswith("."):
            spoken += "."

        return f"{title}: {spoken}"

    except Exception:
        return "I was unable to reach Wikipedia at this time, sir."


# ---------------------------------------------------------------------------
# Translation  (MyMemory — free, no API key, 5 k chars/day)
# ---------------------------------------------------------------------------

# Map natural language to ISO-639-1 codes
_LANG_MAP: dict[str, str] = {
    "spanish":    "es",
    "french":     "fr",
    "german":     "de",
    "italian":    "it",
    "portuguese": "pt",
    "dutch":      "nl",
    "russian":    "ru",
    "japanese":   "ja",
    "chinese":    "zh",
    "korean":     "ko",
    "arabic":     "ar",
    "hindi":      "hi",
    "turkish":    "tr",
    "polish":     "pl",
    "swedish":    "sv",
    "norwegian":  "no",
    "danish":     "da",
    "greek":      "el",
    "hebrew":     "he",
    "thai":       "th",
}


def translate(arg: str) -> str:
    """
    Translate text.
    Argument format: "<text> to <language>"
    Example: "Good morning to Japanese"
    """
    if not _HAS_REQUESTS:
        return "Translation requires the requests library, sir."

    import re
    # Parse "text to language"
    m = re.search(r"^(.+?)\s+to\s+([a-zA-Z]+)\s*$", arg.strip(), re.IGNORECASE)
    if not m:
        return ("I need a phrase and a target language, sir. "
                "For example: 'translate Good morning to French'.")

    text     = m.group(1).strip()
    lang_raw = m.group(2).strip().lower()
    lang_code = _LANG_MAP.get(lang_raw, lang_raw[:2])  # fallback to first 2 chars

    try:
        resp = _requests.get(
            "https://api.mymemory.translated.net/get",
            params={"q": text, "langpair": f"en|{lang_code}"},
            timeout=8,
            headers={"User-Agent": "Jarvis-Assistant/1.0"},
        )
        resp.raise_for_status()
        data        = resp.json()
        translated  = data["responseData"]["translatedText"]
        quality     = int(data["responseData"].get("match", 0) * 100)

        if not translated or translated.lower() == text.lower():
            return f"I couldn't translate that to {lang_raw}, sir."

        return f"In {lang_raw.capitalize()}: {translated}"

    except Exception:
        return f"Translation service is unavailable at the moment, sir."
