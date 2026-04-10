"""Morning briefing skill — aggregates status, weather, notes, and reminders."""

from jarvis.skills.reminders import list_reminders
from jarvis.skills.system_monitor import get_system_info
from jarvis.skills.utils import get_date, get_time, read_notes
from jarvis.skills.weather import get_weather


def get_briefing(location: str = "") -> str:
    """
    Compile a spoken briefing covering time, date, weather, system status,
    recent notes, and active reminders.
    """
    sections: list[str] = []

    sections.append(get_time())
    sections.append(get_date())

    weather = get_weather(location)
    if weather and "unavailable" not in weather.lower():
        sections.append(weather)

    sysinfo = get_system_info()
    if sysinfo and "unavailable" not in sysinfo.lower():
        sections.append(sysinfo)

    notes = read_notes(3)
    if notes and "no notes" not in notes.lower():
        sections.append(notes)

    reminders = list_reminders()
    if reminders and "no active" not in reminders.lower():
        sections.append(reminders)

    if not sections:
        return "All systems are operational, sir. Nothing to report."

    return " ".join(sections)
