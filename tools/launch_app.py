"""Launch a desktop application by name."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess

TOOL = {
    "name": "launch_app",
    "description": (
        "Open a desktop application. Use for 'open Spotify', 'launch VS Code', "
        "'start the calculator', 'open file explorer'. Give the app's common "
        "name. Does NOT open web pages — use open_url for those."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "app": {"type": "string", "description": "App name, e.g. 'spotify', 'notepad'."},
        },
        "required": ["app"],
    },
}

_OS = platform.system()

# common name -> launch target per OS
_ALIASES = {
    "chrome": {"Windows": "chrome", "Darwin": "Google Chrome", "Linux": "google-chrome"},
    "firefox": {"Windows": "firefox", "Darwin": "Firefox", "Linux": "firefox"},
    "edge": {"Windows": "msedge", "Darwin": "Microsoft Edge", "Linux": "microsoft-edge"},
    "vs code": {"Windows": "code", "Darwin": "Visual Studio Code", "Linux": "code"},
    "vscode": {"Windows": "code", "Darwin": "Visual Studio Code", "Linux": "code"},
    "code": {"Windows": "code", "Darwin": "Visual Studio Code", "Linux": "code"},
    "terminal": {"Windows": "wt", "Darwin": "Terminal", "Linux": "x-terminal-emulator"},
    "powershell": {"Windows": "powershell", "Darwin": "Terminal", "Linux": "bash"},
    "notepad": {"Windows": "notepad", "Darwin": "TextEdit", "Linux": "gedit"},
    "calculator": {"Windows": "calc", "Darwin": "Calculator", "Linux": "gnome-calculator"},
    "calc": {"Windows": "calc", "Darwin": "Calculator", "Linux": "gnome-calculator"},
    "explorer": {"Windows": "explorer", "Darwin": "Finder", "Linux": "nautilus"},
    "file explorer": {"Windows": "explorer", "Darwin": "Finder", "Linux": "nautilus"},
    "files": {"Windows": "explorer", "Darwin": "Finder", "Linux": "nautilus"},
    "task manager": {"Windows": "taskmgr", "Darwin": "Activity Monitor", "Linux": "gnome-system-monitor"},
    "settings": {"Windows": "ms-settings:", "Darwin": "System Settings", "Linux": "gnome-control-center"},
    "spotify": {"Windows": "spotify", "Darwin": "Spotify", "Linux": "spotify"},
    "discord": {"Windows": "discord", "Darwin": "Discord", "Linux": "discord"},
    "slack": {"Windows": "slack", "Darwin": "Slack", "Linux": "slack"},
    "vlc": {"Windows": "vlc", "Darwin": "VLC", "Linux": "vlc"},
    "word": {"Windows": "winword", "Darwin": "Microsoft Word", "Linux": "libreoffice"},
    "excel": {"Windows": "excel", "Darwin": "Microsoft Excel", "Linux": "libreoffice"},
    "paint": {"Windows": "mspaint", "Darwin": "TextEdit", "Linux": "gimp"},
}


def _launch(target: str) -> None:
    if _OS == "Windows":
        if target.endswith(":") or "\\" in target or "/" in target:
            os.startfile(target)  # URIs like ms-settings:
        else:
            # 'start' resolves PATH apps and App Execution Aliases (spotify, etc.)
            subprocess.Popen(
                ["cmd", "/c", "start", "", target],
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
    elif _OS == "Darwin":
        subprocess.Popen(["open", "-a", target])
    else:
        subprocess.Popen(target.split())


def run(app: str = "") -> str:
    name = (app or "").strip().lower()
    if not name:
        return "Launch what?"

    target = _ALIASES.get(name, {}).get(_OS, name)

    # On non-Windows, sanity-check the binary exists before claiming success.
    if _OS not in ("Windows", "Darwin") and not shutil.which(target.split()[0]):
        return f"I can't find an app called {app!r}."

    try:
        _launch(target)
    except FileNotFoundError:
        return f"I can't find an app called {app!r}."
    except Exception as exc:  # noqa: BLE001
        return f"I couldn't launch {app!r}: {exc}"
    return f"Opening {app}."
