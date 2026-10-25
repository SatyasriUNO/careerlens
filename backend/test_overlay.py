"""
test_overlay.py  —  Member 5 demo trigger (Windows 10 version 2004 or newer)

Opens a small "copilot-style" window that you can see on the laptop screen but that is
hidden from screen sharing and screenshots. CopilotShield should turn the light red
within about 2 seconds. Close the window and the light turns green again.

Run:   python test_overlay.py
Check: take a screenshot (Win + Shift + S) — this window should be missing or black in it.
"""

import ctypes
import sys
import tkinter as tk

WDA_EXCLUDEFROMCAPTURE = 0x11

if sys.platform != "win32":
    print("This demo works on Windows 10 (version 2004) or newer only.")
    sys.exit(1)

user32 = ctypes.windll.user32

root = tk.Tk()
root.title("Demo Copilot Overlay")
root.geometry("400x150+80+80")
root.attributes("-topmost", True)
root.attributes("-alpha", 0.9)
root.configure(bg="#2B1A7F")

tk.Label(
    root,
    text="Demo AI copilot overlay\nVisible to you, hidden from screen-share",
    font=("Segoe UI", 13, "bold"),
    fg="white",
    bg="#2B1A7F",
).pack(expand=True)

root.update_idletasks()
root.update()

hwnd = user32.GetParent(root.winfo_id())  # the real top-level window handle
applied = user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)

check = ctypes.c_uint32(0)
user32.GetWindowDisplayAffinity(hwnd, ctypes.byref(check))
print(f"Capture exclusion applied: {bool(applied)}  (affinity now = {hex(check.value)})")
if not applied:
    print("Could not hide the window. Windows 10 version 2004 or newer is required.")

root.mainloop()
