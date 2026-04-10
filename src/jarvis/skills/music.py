"""Music control skill — Apple Music and Spotify via AppleScript (macOS)."""

import platform
import re
import subprocess


def _script(code: str) -> str:
    """Run AppleScript and return trimmed stdout."""
    if platform.system() != "Darwin":
        return ""
    r = subprocess.run(["osascript", "-e", code], capture_output=True, text=True)
    return r.stdout.strip()


def control(action: str) -> str:
    """
    Route a natural-language music command.
    Examples: "play", "pause", "next track", "volume 60",
              "what's playing", "play spotify", "shuffle on"
    """
    if platform.system() != "Darwin":
        return "Music control is only available on macOS, sir."

    low = action.lower().strip()

    # Detect target app
    if "spotify" in low:
        app = "Spotify"
        low = low.replace("spotify", "").strip()
    else:
        app = "Music"

    # Play / resume
    if any(w in low for w in ("play", "resume", "start")):
        _script(f'tell application "{app}" to play')
        return "Playing music, sir."

    # Pause
    if "pause" in low:
        _script(f'tell application "{app}" to pause')
        return "Music paused, sir."

    # Stop
    if "stop" in low:
        _script(f'tell application "{app}" to stop')
        return "Music stopped, sir."

    # Next
    if any(w in low for w in ("next", "skip", "forward")):
        _script(f'tell application "{app}" to next track')
        return "Skipping to the next track, sir."

    # Previous
    if any(w in low for w in ("previous", "prev", "back", "last")):
        _script(f'tell application "{app}" to previous track')
        return "Going back to the previous track, sir."

    # Shuffle
    if "shuffle" in low:
        on = "true" if "off" not in low else "false"
        _script(f'tell application "{app}" to set shuffle enabled to {on}')
        return f"Shuffle {'enabled' if on == 'true' else 'disabled'}, sir."

    # Volume
    m = re.search(r"volume\s+(\d+)", low)
    if m:
        lvl = max(0, min(100, int(m.group(1))))
        _script(f'tell application "{app}" to set sound volume to {lvl}')
        return f"Music volume set to {lvl}, sir."

    # What's playing?
    if any(w in low for w in ("what", "current", "now", "playing", "song", "track", "name")):
        track = _script(f'tell application "{app}" to get name of current track')
        artist = _script(f'tell application "{app}" to get artist of current track')
        if track:
            return f"Currently playing {track} by {artist}, sir."
        return f"{app} doesn't appear to be playing anything, sir."

    # Like / love
    if any(w in low for w in ("love", "like", "heart")):
        _script(f'tell application "{app}" to set loved of current track to true')
        return "Marked as loved, sir."

    return "I didn't recognise that music command, sir."
