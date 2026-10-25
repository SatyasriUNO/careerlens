"""
shield.py  —  Member 5 (CopilotShield-lite)

Detects AI interview copilots running on this laptop, WITHOUT using the camera:
  1. Hidden overlay scanner: finds visible windows that hide themselves from screen
     capture (Windows display affinity flag). This is the trick copilot overlays use.
  2. Process scan: finds running apps whose name/path matches data/known_tools.json.

Works on Windows 10 version 2004 or newer. On other systems it reports "unavailable".
It only reads window flags and process names. It never reads window contents.

Used by main.py:
    shield.monitor.start_session(session_id, consent)
    shield.monitor.status()          -> for GET /api/shield/status
    shield.monitor.stop_session()    -> integrity summary for the final report

Check your laptop (prints everything it finds, useful for tuning the allow-list):
    python shield.py
    python shield.py --watch        (scans every 2 seconds until Ctrl+C)
"""

import json
import os
import sys
import threading
import time
from datetime import datetime

import psutil

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "data", "known_tools.json")

IS_WINDOWS = sys.platform == "win32"

WDA_NONE = 0x0
WDA_MONITOR = 0x1
WDA_EXCLUDEFROMCAPTURE = 0x11
DWMWA_CLOAKED = 14
GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008
WS_EX_LAYERED = 0x00080000
MIN_WINDOW_SIZE = 20  # pixels; ignore tiny invisible helper windows
LAST_ERROR = ""  # last unexpected error while reading a window (shown by "python shield.py")

# ---------------------------------------------------------------- Windows API setup
WINDOWS_API_READY = False
if IS_WINDOWS:
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        dwmapi = ctypes.WinDLL("dwmapi")

        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
        user32.EnumWindows.restype = wintypes.BOOL
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.IsIconic.argtypes = [wintypes.HWND]
        user32.IsIconic.restype = wintypes.BOOL
        user32.GetWindowDisplayAffinity.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.GetWindowDisplayAffinity.restype = wintypes.BOOL
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetWindowTextW.restype = ctypes.c_int
        user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        user32.GetWindowRect.restype = wintypes.BOOL
        user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.GetWindowLongW.restype = ctypes.c_long
        dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), wintypes.DWORD]
        dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long

        WINDOWS_API_READY = True
    except (OSError, AttributeError):
        WINDOWS_API_READY = False

AVAILABLE = IS_WINDOWS and WINDOWS_API_READY


# ---------------------------------------------------------------- config
def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        data = {}
    keywords = [k.lower() for k in data.get("process_keywords", []) if k]
    allow = {a.lower() for a in data.get("allow_processes", []) if a}
    return keywords, allow


def _now():
    return datetime.now().strftime("%H:%M:%S")


def _process_name(pid):
    try:
        return psutil.Process(pid).name()
    except (psutil.Error, ValueError):
        return f"pid-{pid}"


# ---------------------------------------------------------------- layer 1: hidden overlays
def _window_info(hwnd):
    """Return details of one visible window, or None if it should be skipped."""
    if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
        return None

    cloaked = wintypes.DWORD(0)
    dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
    if cloaked.value:
        return None  # hidden by Windows itself (background apps), not shown to the user

    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    width, height = rect.right - rect.left, rect.bottom - rect.top
    if width < MIN_WINDOW_SIZE or height < MIN_WINDOW_SIZE:
        return None

    affinity = wintypes.DWORD(0)
    if not user32.GetWindowDisplayAffinity(hwnd, ctypes.byref(affinity)):
        return None

    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

    length = user32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)

    exstyle = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    return {
        "hwnd": int(hwnd) if hwnd else 0,
        "pid": pid.value,
        "title": buffer.value,
        "affinity": affinity.value,
        "topmost": bool(exstyle & WS_EX_TOPMOST),
        "layered": bool(exstyle & WS_EX_LAYERED),
        "size": f"{width}x{height}",
    }


def scan_hidden_windows(allow):
    """Find visible windows that hide themselves from screen capture."""
    if not AVAILABLE:
        return []
    found = []
    own_pid = os.getpid()

    def callback(hwnd, _lparam):
        try:
            info = _window_info(hwnd)
            if info and info["affinity"] in (WDA_MONITOR, WDA_EXCLUDEFROMCAPTURE) and info["pid"] != own_pid:
                name = _process_name(info["pid"])
                if name.lower() not in allow:
                    flags = []
                    if info["topmost"]:
                        flags.append("always on top")
                    if info["layered"]:
                        flags.append("transparent layer")
                    detail = "Window is hidden from screen sharing"
                    if flags:
                        detail += " (" + ", ".join(flags) + ")"
                    found.append({
                        "type": "hidden_overlay",
                        "name": name,
                        "pid": info["pid"],
                        "title": info["title"][:80],
                        "detail": detail,
                    })
        except Exception as exc:  # one odd window must not stop the scan
            global LAST_ERROR
            LAST_ERROR = f"{type(exc).__name__}: {exc}"
        return True  # keep enumerating

    user32.EnumWindows(WNDENUMPROC(callback), 0)
    return found


# ---------------------------------------------------------------- layer 2: known processes
def scan_known_processes(keywords, allow):
    found = []
    if not keywords:
        return found
    for proc in psutil.process_iter(["pid", "name", "exe"]):
        try:
            name = proc.info.get("name") or ""
            exe = proc.info.get("exe") or ""
        except (psutil.Error, KeyError):
            continue
        if name.lower() in allow:
            continue
        text = f"{name} {exe}".lower()
        match = next((k for k in keywords if k in text), None)
        if match:
            found.append({
                "type": "known_process",
                "name": name,
                "pid": proc.info.get("pid"),
                "title": "",
                "detail": f"Matches known copilot signature '{match}'",
            })
    return found


def scan_once():
    keywords, allow = load_config()
    return scan_hidden_windows(allow) + scan_known_processes(keywords, allow)


# ---------------------------------------------------------------- background monitor
class ShieldMonitor:
    def __init__(self, interval=2.0):
        self.interval = interval
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread = None
        self._reset(session_id=None, consent=False)

    def _reset(self, session_id, consent):
        self.session_id = session_id
        self.consent = consent
        self.active = False
        self._current = []
        self._events = []
        self._seen = set()
        self.last_scan = None

    # ----- session control
    def start_session(self, session_id, consent):
        self.stop_session()
        with self._lock:
            self._reset(session_id=session_id, consent=bool(consent))
        if not consent or not AVAILABLE:
            return
        self._stop_event.clear()
        self.active = True
        self._thread = threading.Thread(target=self._run, name="copilot-shield", daemon=True)
        self._thread.start()

    def stop_session(self):
        """Stop scanning and return the integrity summary for the finished session."""
        summary = self.session_summary()
        if self._thread and self._thread.is_alive():
            self._stop_event.set()
            self._thread.join(timeout=5)
        self._thread = None
        self.active = False
        return summary

    # ----- scanning loop
    def _run(self):
        while not self._stop_event.is_set():
            try:
                findings = scan_once()
            except Exception:
                findings = []
            with self._lock:
                self._current = findings
                self.last_scan = _now()
                for f in findings:
                    key = (f["type"], f["pid"], f["name"])
                    if key not in self._seen:
                        self._seen.add(key)
                        self._events.append({**f, "time": self.last_scan})
            self._stop_event.wait(self.interval)

    # ----- reporting
    def _reason(self):
        if not AVAILABLE:
            return "CopilotShield needs Windows 10 (version 2004) or newer"
        if self.session_id and not self.consent:
            return "Student did not give consent for integrity checks"
        if not self.active:
            return "No interview in progress"
        return ""

    def status(self):
        """Live state for the status light. Shape: {status, findings, active, reason, last_scan}."""
        with self._lock:
            if not AVAILABLE or (self.session_id and not self.consent):
                state = "unavailable"
            elif self._current:
                state = "alert"
            else:
                state = "clear"
            findings = [{**f, "time": self.last_scan} for f in self._current]
            return {
                "status": state,
                "findings": findings,
                "active": self.active,
                "reason": self._reason(),
                "last_scan": self.last_scan,
            }

    def session_summary(self):
        """Integrity block for the final report. Shape: {status, events, reason}."""
        with self._lock:
            if not AVAILABLE or not self.consent:
                state = "unavailable"
            elif self._events:
                state = "alert"
            else:
                state = "clear"
            return {"status": state, "events": list(self._events), "reason": self._reason() if state == "unavailable" else ""}


monitor = ShieldMonitor()


# ---------------------------------------------------------------- command-line check
def _print_report():
    print(f"Windows API available: {AVAILABLE}")
    if not AVAILABLE:
        print("CopilotShield will report 'unavailable' on this computer.")
        return
    keywords, allow = load_config()
    hidden = scan_hidden_windows(allow)
    procs = scan_known_processes(keywords, allow)
    print(f"[{_now()}] hidden-from-capture windows: {len(hidden)} | known copilot processes: {len(procs)}")
    for f in hidden + procs:
        print(f"   - {f['type']:15} {f['name']} (pid {f['pid']}) {f['title']!r} -> {f['detail']}")
    if not hidden and not procs:
        print("   Nothing found. Run test_overlay.py in another terminal to see an alert.")
    if LAST_ERROR:
        print(f"   Note: one window could not be read -> {LAST_ERROR}")


if __name__ == "__main__":
    if "--watch" in sys.argv:
        try:
            while True:
                _print_report()
                time.sleep(2)
        except KeyboardInterrupt:
            print("Stopped.")
    else:
        _print_report()
