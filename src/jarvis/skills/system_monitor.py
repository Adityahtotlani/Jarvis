"""System monitoring skill — CPU, RAM, disk, battery, network."""

import platform
import subprocess

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False


def get_system_info() -> str:
    """Return a spoken summary of current system resource usage."""
    if not _HAS_PSUTIL:
        return "System monitoring is unavailable — psutil is not installed, sir."

    parts: list[str] = []

    # CPU
    cpu = psutil.cpu_percent(interval=0.5)
    parts.append(f"CPU at {cpu:.0f} percent")

    # RAM
    ram = psutil.virtual_memory()
    free_gb = ram.available / (1024 ** 3)
    parts.append(f"RAM at {ram.percent:.0f} percent with {free_gb:.1f} gigabytes free")

    # Disk (root)
    try:
        disk = psutil.disk_usage("/")
        parts.append(f"disk at {disk.percent:.0f} percent capacity")
    except Exception:
        pass

    # Battery
    try:
        battery = psutil.sensors_battery()
        if battery is not None:
            status = "charging" if battery.power_plugged else "on battery"
            parts.append(f"battery at {battery.percent:.0f} percent, {status}")
    except Exception:
        pass

    # Uptime
    try:
        boot_time = psutil.boot_time()
        import time
        uptime_sec = time.time() - boot_time
        uptime_h = int(uptime_sec // 3600)
        uptime_m = int((uptime_sec % 3600) // 60)
        if uptime_h > 0:
            parts.append(f"system uptime {uptime_h} hours {uptime_m} minutes")
        else:
            parts.append(f"system uptime {uptime_m} minutes")
    except Exception:
        pass

    return "All systems nominal. " + ", ".join(parts) + "."


def get_cpu_temp() -> str:
    """Best-effort CPU temperature — returns empty string if unavailable."""
    if not _HAS_PSUTIL:
        return ""
    try:
        temps = psutil.sensors_temperatures()
        if not temps:
            return ""
        for key in ("coretemp", "cpu_thermal", "acpitz", "k10temp"):
            if key in temps and temps[key]:
                t = temps[key][0].current
                return f"{t:.0f}°C"
    except Exception:
        pass
    return ""
