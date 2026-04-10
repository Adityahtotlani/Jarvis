"""File skill — read and return content for LLM summarization."""

import os
from pathlib import Path

# Max characters to read before truncating (keeps prompt manageable)
_MAX_CHARS = 8_000

_READABLE_EXTENSIONS = {
    ".txt", ".md", ".py", ".js", ".ts", ".json", ".yaml", ".yml",
    ".toml", ".ini", ".cfg", ".sh", ".bash", ".csv", ".html", ".css",
    ".xml", ".rst", ".log", ".env", ".sql",
}


def read_file(path: str) -> tuple[str, str]:
    """
    Read *path* and return (content, error).
    Returns (content, "") on success, ("", error_message) on failure.
    """
    path = path.strip().strip("'\"")
    expanded = Path(os.path.expanduser(path)).resolve()

    # Safety: don't read outside home directory
    home = Path.home().resolve()
    try:
        expanded.relative_to(home)
    except ValueError:
        # Allow /tmp and common project dirs too
        if not str(expanded).startswith("/tmp"):
            return "", f"I can only read files within your home directory, sir."

    if not expanded.exists():
        return "", f"I couldn't find the file at {path}, sir."

    if expanded.is_dir():
        # List directory contents instead
        try:
            entries = sorted(expanded.iterdir())
            names   = [e.name + ("/" if e.is_dir() else "") for e in entries[:50]]
            listing = ", ".join(names)
            return f"Directory listing for {expanded}: {listing}", ""
        except PermissionError:
            return "", f"I don't have permission to read that directory, sir."

    if expanded.suffix.lower() not in _READABLE_EXTENSIONS:
        return "", (
            f"I can't read {expanded.suffix} files, sir. "
            "I support text, code, JSON, YAML, and similar formats."
        )

    size = expanded.stat().st_size
    if size > 500_000:  # 500 KB hard limit
        return "", f"That file is {size // 1024} KB — too large to read directly, sir."

    try:
        content = expanded.read_text(encoding="utf-8", errors="replace")
    except PermissionError:
        return "", f"I don't have permission to read that file, sir."
    except Exception as e:
        return "", f"I encountered an error reading the file: {e}"

    if len(content) > _MAX_CHARS:
        content = content[:_MAX_CHARS] + f"\n\n[… truncated at {_MAX_CHARS} characters]"

    return content, ""


def safe_python(code: str) -> str:
    """
    Execute a Python expression or short script in a subprocess.
    Returns stdout (first 500 chars) or the error message.
    Times out after 8 seconds.
    """
    import subprocess
    import sys

    # Block obviously dangerous patterns
    blocked = [
        "import os", "import sys", "import subprocess",
        "open(", "__import__", "exec(", "eval(",
        "shutil", "socket", "urllib", "requests",
    ]
    for b in blocked:
        if b in code:
            return f"That code contains a restricted operation ({b!r}), sir."

    try:
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=8,
        )
        output = (result.stdout or result.stderr or "No output.").strip()
        return output[:500] + ("…" if len(output) > 500 else "")
    except subprocess.TimeoutExpired:
        return "That code took too long to execute, sir."
    except Exception as e:
        return f"Execution failed: {e}"
