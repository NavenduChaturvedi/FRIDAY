"""How the machine is doing — CPU, memory, disk, battery."""

from __future__ import annotations

TOOL = {
    "name": "system_status",
    "description": (
        "Report the computer's health: CPU load, memory use, disk space, and "
        "battery. Use for 'how's my CPU', 'am I running out of memory', 'how "
        "much battery', 'is my disk full'."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "what": {
                "type": "string",
                "enum": ["all", "cpu", "memory", "disk", "battery"],
                "description": "Which metric; default 'all'.",
            },
        },
        "required": [],
    },
}


def _cpu(psutil) -> str:
    pct = psutil.cpu_percent(interval=0.4)
    return f"CPU load is {pct:.0f}%"


def _memory(psutil) -> str:
    m = psutil.virtual_memory()
    return f"memory is {m.percent:.0f}% used ({m.used / 1e9:.1f} of {m.total / 1e9:.1f} GB)"


def _disk(psutil) -> str:
    import os

    d = psutil.disk_usage(os.path.expanduser("~"))
    return f"the main disk is {d.percent:.0f}% full, {d.free / 1e9:.0f} GB free"


def _battery(psutil) -> str:
    b = getattr(psutil, "sensors_battery", lambda: None)()
    if b is None:
        return "there's no battery (or I can't read it)"
    state = "charging" if b.power_plugged else "on battery"
    if b.percent is None:
        return f"battery status: {state}"
    extra = ""
    if not b.power_plugged and b.secsleft and b.secsleft > 0:
        extra = f", about {b.secsleft // 3600}h {b.secsleft % 3600 // 60}m left"
    return f"battery is at {b.percent:.0f}%, {state}{extra}"


def run(what: str = "all") -> str:
    try:
        import psutil
    except ImportError:
        return "System monitoring isn't available — the psutil package isn't installed."

    what = (what or "all").strip().lower()
    parts = {"cpu": _cpu, "memory": _memory, "disk": _disk, "battery": _battery}

    try:
        if what in parts:
            sentence = parts[what](psutil)
        else:
            sentence = "; ".join(fn(psutil) for fn in parts.values())
    except Exception as exc:  # noqa: BLE001
        return f"I couldn't read the system stats: {exc}"

    return sentence[:1].upper() + sentence[1:] + "."
