"""
prewarm.py  —  Member 5. Run 5 minutes before the demo, while the backend is running.

Loads the LLM into memory (so the first question is fast) and checks every part.
Run:  python prewarm.py
"""

import time

import requests

import llm

BACKEND = "http://localhost:8000"

print("1/3  Loading the LLM into memory (can take up to a minute the first time)...")
start = time.time()
reply = llm.ask_llm("Reply with the single word: ready")
print(f"     LLM replied {reply.strip()[:40]!r} in {time.time() - start:.1f} s")

print("2/3  Checking the backend...")
try:
    health = requests.get(f"{BACKEND}/api/health", timeout=10).json()
    for key, value in health.items():
        print(f"     {key}: {value}")
except requests.RequestException:
    print("     Backend is NOT running. Start it with:  uvicorn main:app --port 8000")

print("3/3  Checking CopilotShield...")
try:
    status = requests.get(f"{BACKEND}/api/shield/status", timeout=10).json()
    print(f"     status: {status.get('status')}  {status.get('reason', '')}")
except requests.RequestException:
    print("     Could not reach /api/shield/status")

print("Done. If everything above looks right, you are ready to demo.")
