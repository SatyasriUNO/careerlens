"""
llm.py  —  shared gateway to the local Ollama model (owned by Member 5, frozen)

Every module calls ask_llm(). Nobody else talks to Ollama directly.
Test:  python llm.py
"""

import json
import requests

OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"
MODEL = "qwen2.5:3b"  # change to "qwen2.5:1.5b" on weak laptops


def ask_llm(prompt, system="You are a helpful career coach.", want_json=False, temperature=0.3):
    """Send a prompt to the local Ollama model.
    Returns a dict when want_json=True, otherwise a string.
    Never raises: on failure returns {"error": ...} or an empty string."""
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "keep_alive": -1,  # keep the model loaded in memory
        "options": {"temperature": temperature},
    }
    if want_json:
        payload["format"] = "json"

    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=180)
        response.raise_for_status()
        text = response.json()["message"]["content"]
    except Exception as exc:
        return {"error": f"llm_unavailable: {exc}"} if want_json else ""

    if not want_json:
        return text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"error": "invalid_json", "raw": text}


def is_ollama_up():
    try:
        return requests.get(OLLAMA_TAGS_URL, timeout=3).ok
    except Exception:
        return False


if __name__ == "__main__":
    print("Ollama running:", is_ollama_up())
    print(ask_llm('Give 3 interview tips as JSON: {"tips": []}', want_json=True))
