"""Dictionary skill — word definitions via Free Dictionary API (no key)."""

try:
    import requests as _requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False


def define(word: str) -> str:
    """Fetch a spoken definition of *word*."""
    if not _HAS_REQUESTS:
        return "Dictionary lookup requires the requests library, sir."

    word = word.strip().lower().strip("'\".")
    if not word:
        return "Please specify a word to define, sir."

    try:
        resp = _requests.get(
            f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}",
            timeout=8,
            headers={"User-Agent": "Jarvis-Assistant/1.0"},
        )
        if resp.status_code == 404:
            return f"I couldn't find a definition for '{word}', sir."
        resp.raise_for_status()
        data = resp.json()

        if not data:
            return f"No definition found for '{word}', sir."

        entry    = data[0]
        meanings = entry.get("meanings", [])
        if not meanings:
            return f"The dictionary had no meanings for '{word}', sir."

        meaning        = meanings[0]
        part_of_speech = meaning.get("partOfSpeech", "")
        definitions    = meaning.get("definitions", [])
        if not definitions:
            return f"No definitions found for '{word}', sir."

        definition = definitions[0].get("definition", "").strip()
        example    = definitions[0].get("example", "").strip()

        pos = f" ({part_of_speech})" if part_of_speech else ""
        result = f"{word.capitalize()}{pos}: {definition}"
        if example:
            result += f" For example: {example}"
        return result

    except Exception:
        return f"I couldn't retrieve a definition for '{word}', sir."
