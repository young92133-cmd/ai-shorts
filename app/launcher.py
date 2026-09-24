"""Double-click launcher for the local web app."""
from __future__ import annotations

import json
import os
import socket
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
URL = "http://127.0.0.1:8765/"


def _refresh_user_path() -> None:
    """Explorer may have an old PATH after installing Claude Code or ffmpeg."""
    if os.name != "nt":
        return
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            user_path, _ = winreg.QueryValueEx(key, "Path")
    except OSError:
        return
    os.environ["PATH"] = os.pathsep.join((os.environ.get("PATH", ""), os.path.expandvars(user_path)))


def _our_server_is_ready() -> bool:
    try:
        with urllib.request.urlopen(URL + "openapi.json", timeout=1) as response:
            return json.load(response).get("info", {}).get("title") == "AI Shorts"
    except (OSError, ValueError, urllib.error.URLError):
        return False


def _port_is_in_use() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex(("127.0.0.1", 8765)) == 0


def _open_browser_when_ready(stop: threading.Event) -> None:
    for _ in range(120):
        if stop.is_set():
            return
        if _our_server_is_ready():
            print(f"Opening browser: {URL}", flush=True)
            webbrowser.open(URL)
            return
        time.sleep(0.5)
    print(f"Browser did not open automatically. Visit {URL}", flush=True)


def main() -> int:
    os.chdir(ROOT)
    _refresh_user_path()
    if _our_server_is_ready():
        print("AI Shorts is already running. Opening browser...", flush=True)
        webbrowser.open(URL)
        return 0
    if _port_is_in_use():
        print("Port 8765 is being used by another program. Close it and try again.", flush=True)
        return 1

    try:
        import uvicorn
    except ImportError:
        print("Required Python packages are missing. Install requirements.txt first.", flush=True)
        return 1

    print("Starting AI Shorts...", flush=True)
    print("Keep this window open while using the app. Closing it stops the app.", flush=True)
    stop = threading.Event()
    opener = threading.Thread(target=_open_browser_when_ready, args=(stop,), daemon=True)
    opener.start()
    try:
        uvicorn.run("app.main:app", host="127.0.0.1", port=8765, log_level="info")
    except (OSError, RuntimeError) as exc:
        print(f"Could not start AI Shorts: {exc}", flush=True)
        return 1
    finally:
        stop.set()
        opener.join(timeout=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
