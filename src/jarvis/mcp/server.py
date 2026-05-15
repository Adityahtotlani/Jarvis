"""J.A.R.V.I.S. MCP Server — exposes all Jarvis skills as MCP tools.

Run with:
    python -m jarvis.mcp.server
or via the CLI entry point:
    jarvis-mcp

Then add to Claude Desktop config:
    {
      "mcpServers": {
        "jarvis": {
          "command": "python3",
          "args": ["-m", "jarvis.mcp.server"],
          "cwd": "/path/to/Jarvis/src"
        }
      }
    }
"""

import sys
import os

# Ensure the src package is on the path when run directly
_here = os.path.dirname(os.path.abspath(__file__))
_src  = os.path.join(_here, "..", "..", "..")
if _src not in sys.path:
    sys.path.insert(0, _src)

from mcp.server import FastMCP

mcp = FastMCP("J.A.R.V.I.S.")


# ---------------------------------------------------------------------------
# Time & Date
# ---------------------------------------------------------------------------

@mcp.tool()
def get_time() -> str:
    """Return the current local time."""
    from jarvis.skills.utils import get_time as _get_time
    return _get_time()


@mcp.tool()
def get_date() -> str:
    """Return today's date."""
    from jarvis.skills.utils import get_date as _get_date
    return _get_date()


# ---------------------------------------------------------------------------
# Calculations
# ---------------------------------------------------------------------------

@mcp.tool()
def calculate(expression: str) -> str:
    """Evaluate a mathematical expression (e.g. '2 ** 10 + sqrt(144)')."""
    from jarvis.skills.utils import calculate as _calc
    return _calc(expression)


# ---------------------------------------------------------------------------
# Weather
# ---------------------------------------------------------------------------

@mcp.tool()
def get_weather(location: str = "") -> str:
    """Fetch current weather for a location. Leave blank for local weather."""
    from jarvis.skills.weather import get_weather as _weather
    return _weather(location)


# ---------------------------------------------------------------------------
# Web search & news
# ---------------------------------------------------------------------------

@mcp.tool()
def web_search(query: str) -> str:
    """Search the web using DuckDuckGo and return a summary of results."""
    from jarvis.skills.web_search import search
    return search(query)


# ---------------------------------------------------------------------------
# Wikipedia
# ---------------------------------------------------------------------------

@mcp.tool()
def wikipedia_summary(topic: str) -> str:
    """Fetch a Wikipedia summary for the given topic."""
    from jarvis.skills.lookup import wikipedia
    return wikipedia(topic)


# ---------------------------------------------------------------------------
# Translation
# ---------------------------------------------------------------------------

@mcp.tool()
def translate(text_and_language: str) -> str:
    """Translate text. Format: '<text> to <language>' e.g. 'Hello to Spanish'."""
    from jarvis.skills.lookup import translate as _translate
    return _translate(text_and_language)


# ---------------------------------------------------------------------------
# Unit conversion
# ---------------------------------------------------------------------------

@mcp.tool()
def convert_units(expression: str) -> str:
    """Convert between units. Example: '5 miles to km', '100 fahrenheit to celsius'."""
    from jarvis.skills.convert import convert
    return convert(expression)


# ---------------------------------------------------------------------------
# Dictionary
# ---------------------------------------------------------------------------

@mcp.tool()
def define_word(word: str) -> str:
    """Look up the definition of a word."""
    from jarvis.skills.dictionary import define
    return define(word)


# ---------------------------------------------------------------------------
# Market data
# ---------------------------------------------------------------------------

@mcp.tool()
def get_stock_quote(symbol: str) -> str:
    """Fetch a real-time stock quote. Example: 'AAPL', 'TSLA'."""
    from jarvis.skills.market import get_stock
    return get_stock(symbol)


@mcp.tool()
def get_crypto_price(coin: str) -> str:
    """Fetch a crypto price. Example: 'bitcoin', 'ethereum', 'BTC'."""
    from jarvis.skills.market import get_crypto
    return get_crypto(coin)


# ---------------------------------------------------------------------------
# System info
# ---------------------------------------------------------------------------

@mcp.tool()
def get_system_info() -> str:
    """Report CPU, RAM, disk, and battery status."""
    from jarvis.skills.system_monitor import get_system_info as _sysinfo
    return _sysinfo()


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------

@mcp.tool()
def add_note(text: str) -> str:
    """Save a note to the notes file."""
    from jarvis.skills.utils import add_note as _add
    return _add(text)


@mcp.tool()
def read_notes() -> str:
    """Read all saved notes."""
    from jarvis.skills.utils import read_notes as _read
    return _read()


# ---------------------------------------------------------------------------
# Reminders
# ---------------------------------------------------------------------------

@mcp.tool()
def set_reminder(message: str, minutes: float) -> str:
    """Schedule a reminder to fire after the given number of minutes."""
    from jarvis.skills.reminders import set_reminder as _remind
    return _remind(message, minutes)


@mcp.tool()
def set_reminder_natural(reminder_text: str) -> str:
    """Set a reminder using natural language.

    Examples:
      'buy milk in 15 minutes'
      'call John at 3pm'
      'check email tomorrow at 9am'
      'take medication in 2 hours'
    """
    from jarvis.skills.reminders import parse_remind_arg, set_reminder as _remind
    msg, mins = parse_remind_arg(reminder_text)
    return _remind(msg, mins)


@mcp.tool()
def list_reminders() -> str:
    """List all active reminders."""
    from jarvis.skills.reminders import list_reminders as _list
    return _list()


# ---------------------------------------------------------------------------
# Timers
# ---------------------------------------------------------------------------

@mcp.tool()
def start_timer(duration: str) -> str:
    """Start a countdown timer. Example: '5 minutes', '1 hour 30 minutes', '90 seconds'."""
    from jarvis.skills.timer import start
    return start(duration)


@mcp.tool()
def list_timers() -> str:
    """List all active countdown timers."""
    from jarvis.skills.timer import list_active
    return list_active()


@mcp.tool()
def cancel_all_timers() -> str:
    """Cancel all active countdown timers."""
    from jarvis.skills.timer import cancel_all
    return cancel_all()


# ---------------------------------------------------------------------------
# Jokes
# ---------------------------------------------------------------------------

@mcp.tool()
def get_joke() -> str:
    """Fetch a random joke."""
    from jarvis.skills.jokes import get_joke as _joke
    return _joke()


# ---------------------------------------------------------------------------
# Clipboard
# ---------------------------------------------------------------------------

@mcp.tool()
def read_clipboard() -> str:
    """Read the current contents of the system clipboard."""
    from jarvis.skills.clipboard import read_clipboard as _read
    return _read()


@mcp.tool()
def write_clipboard(text: str) -> str:
    """Write text to the system clipboard."""
    from jarvis.skills.clipboard import write_clipboard as _write
    return _write(text)


# ---------------------------------------------------------------------------
# File operations
# ---------------------------------------------------------------------------

@mcp.tool()
def read_file(path: str) -> str:
    """Read a file and return its contents. Path must be absolute or relative to cwd."""
    from jarvis.skills.files import read_file as _rf
    content, err = _rf(path)
    if err:
        return err
    return content


@mcp.tool()
def run_python(code: str) -> str:
    """Execute a Python expression or short snippet and return stdout/result."""
    from jarvis.skills.files import safe_python
    return safe_python(code)


# ---------------------------------------------------------------------------
# System control
# ---------------------------------------------------------------------------

@mcp.tool()
def open_application(name: str) -> str:
    """Open an application by name (e.g. 'Safari', 'Terminal', 'Chrome')."""
    from jarvis.skills import system_control
    return system_control.open_app(name)


@mcp.tool()
def open_url(url: str) -> str:
    """Open a URL in the default web browser."""
    from jarvis.skills import system_control
    return system_control.open_url(url)


@mcp.tool()
def set_volume(level: int) -> str:
    """Set the system volume (0-100)."""
    from jarvis.skills import system_control
    return system_control.set_volume(level)


@mcp.tool()
def run_shell_command(command: str) -> str:
    """Execute a shell command and return its output."""
    from jarvis.skills import system_control
    return system_control.run_command(command)


@mcp.tool()
def lock_screen() -> str:
    """Lock the computer screen."""
    from jarvis.skills import system_control
    return system_control.lock_screen()


@mcp.tool()
def sleep_computer() -> str:
    """Put the computer to sleep."""
    from jarvis.skills import system_control
    return system_control.sleep_computer()


# ---------------------------------------------------------------------------
# Vision (screen analysis via Ollama LLaVA)
# ---------------------------------------------------------------------------

@mcp.tool()
def analyze_screen(question: str = "") -> str:
    """Capture the screen and describe it, or answer a specific question about it."""
    from jarvis.skills.vision import analyze_screen as _vision
    return _vision(question)


# ---------------------------------------------------------------------------
# Briefing
# ---------------------------------------------------------------------------

@mcp.tool()
def get_briefing() -> str:
    """Deliver a full morning briefing: time, weather, news summary."""
    from jarvis.skills.briefing import get_briefing as _brief
    return _brief()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
