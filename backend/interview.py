"""
interview.py  —  Member 3 (Interview Engine + Whisper). Fixed version, same public API.

Public functions (used by main.py):
    start_plan(parsed_resume, role)        -> list of 5 question dicts (q1..q5)
    evaluate_answer(question, transcript)  -> evaluation dict
    transcribe(audio_path)                 -> {"transcript": str, "speech": {...} | None}
    whisper_ready()                        -> bool (loads the Whisper model once)

Notes for main.py:
  * Technical questions carry "key_points". Keep the full plan in the session, strip
    key_points before sending to the browser, and pass the stored dict to evaluate_answer.
  * transcribe() never raises. Failure -> {"transcript": "", "speech": None}.
  * If the LLM is unavailable, evaluate_answer returns score/clarity = None (shown as
    "Not scored") instead of inventing a number.

Self-test:  python interview.py
"""

import json
import random
import re
import string
import threading
from pathlib import Path

from llm import ask_llm

ROLES = ("SDE", "Data Analyst", "ML Engineer", "Embedded", "Web Developer")
DEFAULT_ROLE = "SDE"
WHISPER_MODEL = "base.en"
FILLER_WORDS = {"um", "uh", "like", "basically", "actually"}
LONG_PAUSE_S = 2.0
MAX_BULLET_IN_QUESTION = 160

_BANK = None
_model = None
_model_lock = threading.Lock()


# ------------------------------------------------------------------ question bank
def _load_bank():
    global _BANK
    if _BANK is None:
        path = Path(__file__).parent / "data" / "question_bank.json"
        with open(path, encoding="utf-8") as f:
            _BANK = json.load(f)
    return _BANK


def _resolve_role(role):
    """Case-insensitive match to one of the 5 roles, else SDE."""
    wanted = str(role or "").strip().lower()
    for r in ROLES:
        if r.lower() == wanted:
            return r
    return DEFAULT_ROLE


def _q_text(item, default):
    if not isinstance(item, dict):
        return default
    return item.get("question") or item.get("text") or default


# ------------------------------------------------------------------ resume claims
def _collect_bullets(parsed_resume):
    """All bullets from projects and experience, measurable ones (with numbers) first."""
    parsed = parsed_resume if isinstance(parsed_resume, dict) else {}
    bullets = []
    for section in ("experience", "projects"):
        for entry in parsed.get(section) or []:
            if not isinstance(entry, dict):
                continue
            for b in entry.get("bullets") or []:
                if isinstance(b, str) and len(b.split()) >= 4 and b.strip() not in bullets:
                    bullets.append(b.strip())
    measurable = [b for b in bullets if re.search(r"\d|%", b)]
    others = [b for b in bullets if b not in measurable]
    return measurable + others


def _shorten(text, limit=MAX_BULLET_IN_QUESTION):
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def _template_question(bullet):
    quoted = _shorten(bullet)
    if re.search(r"\d|%", bullet):
        return f"Your resume says: \u201c{quoted}\u201d. How did you measure that result, and what exactly did you do?"
    return f"Your resume says: \u201c{quoted}\u201d. Walk me through what you personally built and the hardest part."


def _claim_questions(parsed_resume):
    """Two DIFFERENT claim-probe questions. The LLM picks bullets by number; templates are the fallback."""
    bullets = _collect_bullets(parsed_resume)[:12]
    chosen = []  # list of (bullet, question)

    if bullets:
        numbered = "\n".join(f"{i + 1}. {b}" for i, b in enumerate(bullets))
        prompt = (
            "These are bullet points from a student's resume:\n"
            f"{numbered}\n\n"
            "Pick the 2 most specific, measurable claims (two different bullets). For each, write one probing "
            "interview question that asks HOW the student achieved or measured it. Quote the key number if there is one.\n"
            'Return JSON only: {"claims": [{"bullet": <number>, "question": "..."}]}'
        )
        result = ask_llm(prompt, system="You are an experienced technical interviewer.", want_json=True)
        claims = result.get("claims", []) if isinstance(result, dict) and "error" not in result else []
        for c in claims if isinstance(claims, list) else []:
            if not isinstance(c, dict):
                continue
            try:
                idx = int(c.get("bullet")) - 1
            except (TypeError, ValueError):
                continue
            question = c.get("question")
            if 0 <= idx < len(bullets) and isinstance(question, str) and len(question.split()) >= 5:
                bullet = bullets[idx]
                if bullet not in [b for b, _ in chosen]:
                    chosen.append((bullet, question.strip()))
            if len(chosen) == 2:
                break

    # Fill any gap with template questions on bullets not used yet
    for bullet in bullets:
        if len(chosen) == 2:
            break
        if bullet not in [b for b, _ in chosen]:
            chosen.append((bullet, _template_question(bullet)))

    # Still short (fewer than 2 usable bullets): generic project questions
    fallback = [_q_text(f, "") for f in _load_bank().get("fallback_project", [])]
    fallback = [f for f in fallback if f] or ["Walk me through a project on your resume. What was the goal?"]
    i = 0
    while len(chosen) < 2:
        chosen.append(("", fallback[i % len(fallback)]))
        i += 1

    return [
        {"id": f"q{n + 2}", "index": n + 2, "total": 5, "type": "claim_probe", "text": q}
        for n, (_, q) in enumerate(chosen[:2])
    ]


# ------------------------------------------------------------------ plan
def start_plan(parsed_resume, role):
    """5 questions: intro, 2 resume-claim probes, 1 technical (for the role), 1 behavioural."""
    bank = _load_bank()
    role = _resolve_role(role)

    intro = {"id": "q1", "index": 1, "total": 5, "type": "intro",
             "text": bank.get("intro", "Tell me about yourself and why you want this role.")}

    try:
        claims = _claim_questions(parsed_resume)
    except Exception as exc:
        print(f"[interview] claim questions failed: {exc}")
        claims = [
            {"id": "q2", "index": 2, "total": 5, "type": "claim_probe", "text": "Walk me through a project on your resume. What was the goal?"},
            {"id": "q3", "index": 3, "total": 5, "type": "claim_probe", "text": "What was your specific role in that project and what did you build?"},
        ]

    technical_bank = bank.get("technical") or {}
    technical_pool = technical_bank.get(role) or technical_bank.get(DEFAULT_ROLE) or []
    tech = random.choice(technical_pool) if technical_pool else {}
    technical = {"id": "q4", "index": 4, "total": 5, "type": "technical",
                 "text": _q_text(tech, "Explain a core concept from your field to a beginner."),
                 "key_points": list(tech.get("key_points", [])) if isinstance(tech, dict) else []}

    behavioural_pool = bank.get("behavioural") or []
    beh = random.choice(behavioural_pool) if behavioural_pool else {}
    behavioural = {"id": "q5", "index": 5, "total": 5, "type": "behavioural",
                   "text": _q_text(beh, "Tell me about a time you solved a difficult problem in a team.")}

    return [intro] + claims + [technical, behavioural]


# ------------------------------------------------------------------ evaluation
def _words(text):
    return set(re.findall(r"[a-z0-9]+", str(text).lower()))


def _to_score(value):
    """Accept 7, 7.5, "7", "7/10". Returns int 1-10 or None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        match = re.search(r"\d+(\.\d+)?", str(value or ""))
        if not match:
            return None
        number = float(match.group())
    return max(1, min(10, int(round(number))))


def _str_list(value, limit=5):
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if str(v).strip()][:limit]


def _uncovered_key_points(question, transcript):
    """Key points whose important words (4+ letters) mostly do not appear in the answer."""
    said = _words(transcript)
    missing = []
    for kp in question.get("key_points", []) or []:
        important = {w for w in _words(kp) if len(w) >= 4} or _words(kp)
        covered = len(important & said) / max(1, len(important))
        if covered < 0.5:
            missing.append(kp)
    return missing


def _fallback_evaluation(question, transcript):
    return {
        "score": None,
        "clarity": None,
        "strengths": [],
        "missing_points": _uncovered_key_points(question, transcript),
        "better_answer": "",
        "note": "AI feedback was not available for this answer.",
    }


def evaluate_answer(question, transcript):
    """Grade one answer with the LLM. Never raises."""
    question = question if isinstance(question, dict) else {"text": str(question)}
    transcript = str(transcript or "").strip()
    try:
        key_points = question.get("key_points") or []
        prompt = (
            "Grade this interview answer from a student.\n"
            f"Question type: {question.get('type', 'general')}\n"
            f"Question: {question.get('text', '')}\n"
            f"Answer: {transcript}\n"
        )
        if key_points:
            prompt += f"Grade against these facts, not the tone. Key points: {key_points}\n"
        prompt += (
            "Return JSON only with exactly these keys: "
            '{"score": 1-10, "clarity": 1-10, "strengths": ["..."], "missing_points": ["..."], '
            '"better_answer": "a short improved answer in first person"}'
        )
        result = ask_llm(prompt, system="You are a fair but strict interviewer. Reply with JSON only.", want_json=True)
        if not isinstance(result, dict) or "error" in result:
            return _fallback_evaluation(question, transcript)

        score, clarity = _to_score(result.get("score")), _to_score(result.get("clarity"))
        if score is None or clarity is None:
            return _fallback_evaluation(question, transcript)

        evaluation = {
            "score": score,
            "clarity": clarity,
            "strengths": _str_list(result.get("strengths")),
            "missing_points": _str_list(result.get("missing_points")),
            "better_answer": str(result.get("better_answer") or "").strip()[:800],
        }
        if len(transcript.split()) < 10:  # very short answers cannot score well
            evaluation["score"] = min(evaluation["score"], 3)
            evaluation["clarity"] = min(evaluation["clarity"], 3)
        return evaluation
    except Exception as exc:
        print(f"[interview] evaluate_answer failed: {exc}")
        return _fallback_evaluation(question, transcript)


# ------------------------------------------------------------------ speech
def whisper_ready():
    """Load the Whisper model once (thread-safe). Returns True when ready."""
    global _model
    if _model is not None:
        return True
    with _model_lock:
        if _model is not None:
            return True
        try:
            from faster_whisper import WhisperModel
            _model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
            return True
        except Exception as exc:
            print(f"[interview] Whisper could not load: {exc}")
            return False


MIN_AUDIO_BYTES = 2000


def _decode_with_av(audio_path, sampling_rate=16000):
    """Read any audio file into 16 kHz mono float32 using PyAV directly.
    Used when faster-whisper's own decoder fails (PyAV 19 removed an option it relies on)."""
    import av
    import numpy as np

    resampler = av.audio.resampler.AudioResampler(format="s16", layout="mono", rate=sampling_rate)
    chunks = []
    with av.open(audio_path, mode="r") as container:
        frames = container.decode(audio=0)
        while True:
            try:
                frame = next(frames)
            except StopIteration:
                break
            except av.error.InvalidDataError:
                continue  # browsers sometimes write one bad frame; skip it
            for out in resampler.resample(frame):
                chunks.append(out.to_ndarray().reshape(-1))
        for out in resampler.resample(None):
            chunks.append(out.to_ndarray().reshape(-1))
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(chunks).astype(np.float32) / 32768.0


def decode_audio_file(audio_path):
    """16 kHz mono float32 audio. Tries faster-whisper's decoder, then our own."""
    try:
        from faster_whisper import decode_audio
        return decode_audio(audio_path, sampling_rate=16000)
    except Exception as first_error:
        try:
            return _decode_with_av(audio_path)
        except Exception as second_error:
            raise RuntimeError(f"{first_error} / {second_error}") from second_error


def _fail(code, detail=""):
    """Failed transcription. code: model_not_loaded | too_short | decode_failed | no_speech | error"""
    return {"transcript": "", "speech": None, "error": code, "detail": str(detail)[:300]}


def transcribe(audio_path):
    """Speech -> text + delivery numbers. Never raises.
    On failure returns {"transcript": "", "speech": None, "error": <code>, "detail": <text>}."""
    try:
        import os
        size = os.path.getsize(audio_path) if os.path.exists(audio_path) else 0
        if size < MIN_AUDIO_BYTES:
            return _fail("too_short", f"audio file is {size} bytes")
        if not whisper_ready():
            return _fail("model_not_loaded", "Whisper model could not be loaded")

        try:
            audio = decode_audio_file(audio_path)
        except Exception as exc:
            return _fail("decode_failed", exc)
        if audio is None or len(audio) < 16000 * 0.5:
            return _fail("too_short", "less than half a second of audio")

        loudest = float(abs(audio).max()) if len(audio) else 0.0
        if loudest < 0.01:
            return _fail("no_speech", f"recording is silent (peak level {loudest:.4f})")

        segments, info = _model.transcribe(
            audio,
            language="en",
            word_timestamps=True,
            beam_size=1,
            condition_on_previous_text=False,
            # This prompt makes Whisper keep filler words instead of cleaning them up
            initial_prompt="Um, so, uh, I like, you know, basically worked on it, actually.",
        )
        words = []
        for seg in segments:
            for w in seg.words or []:
                words.append({"word": w.word, "start": w.start, "end": w.end})
        if not words:
            return _fail("no_speech", f"no words recognised in {len(audio) / 16000:.1f} s of audio (peak level {loudest:.3f})")

        transcript = re.sub(r"\s+", " ", "".join(w["word"] for w in words)).strip()

        filler_count, i = 0, 0
        while i < len(words):
            cleaned = words[i]["word"].lower().strip(string.punctuation + " ")
            following = words[i + 1]["word"].lower().strip(string.punctuation + " ") if i + 1 < len(words) else ""
            if cleaned in FILLER_WORDS:
                filler_count += 1
            elif cleaned == "you" and following == "know":
                filler_count += 1
                i += 1
            i += 1

        long_pauses = sum(1 for j in range(1, len(words)) if words[j]["start"] - words[j - 1]["end"] > LONG_PAUSE_S)
        spoken_s = max(0.0, words[-1]["end"] - words[0]["start"])
        wpm = round(len(words) / (spoken_s / 60.0)) if spoken_s > 0 else 0
        duration = float(getattr(info, "duration", 0) or len(audio) / 16000)

        return {
            "transcript": transcript,
            "speech": {"wpm": wpm, "filler_count": filler_count, "long_pauses": long_pauses, "duration_s": round(duration, 1)},
        }
    except Exception as exc:
        print(f"[interview] transcribe failed: {exc}")
        return _fail("error", exc)


# ------------------------------------------------------------------ self-test
if __name__ == "__main__":
    resume = {"projects": [{"title": "Library App", "bullets": [
        "Built a REST API serving 500 students with JWT authentication",
        "Reduced page load time by 40% using database indexes",
        "Wrote unit tests for the booking module"]}]}
    for role in ROLES:
        plan = start_plan(resume, role)
        print(f"\n{role}:")
        for q in plan:
            print(f"  {q['id']} {q['type']:12} {q['text'][:95]}")
    print("\nEmpty resume:", [q["text"][:50] for q in start_plan({}, "SDE")[1:3]])
    q = {"text": "What is the volatile keyword in C?", "type": "technical",
         "key_points": ["Tells the compiler the value can change outside program flow", "Used for hardware registers and ISR-shared variables"]}
    print("\nEvaluate:", evaluate_answer(q, "volatile tells the compiler the value can change, used for hardware registers"))
    print("Whisper ready:", whisper_ready())
