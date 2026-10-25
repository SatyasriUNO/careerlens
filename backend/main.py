"""
main.py  —  Member 5. The FastAPI app. Only Member 5 edits this file.

Run (from the backend folder, with the venv active):
    uvicorn main:app --port 8000
Open http://localhost:8000/docs to try every endpoint in the browser.

Design rule: every call into another member's module goes through an "adapter" below.
If a module crashes or its function signature is different, the adapter prints a clear
message in this terminal and uses a safe fallback, so the demo never stops.
"""

import os
import shutil
import threading
import traceback
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import db
import gaze as gaze_mod
import llm
import shield

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUDIO_DIR = os.path.join(BASE_DIR, "data", "audio")
os.makedirs(AUDIO_DIR, exist_ok=True)

# ------------------------------------------------------------------ import team modules safely
IMPORT_ERRORS = {}


def _safe_import(name):
    try:
        return __import__(name)
    except Exception as exc:  # noqa: BLE001 - we want to keep the server alive
        IMPORT_ERRORS[name] = f"{type(exc).__name__}: {exc}"
        print(f"\n[main] WARNING: could not import {name}.py -> {IMPORT_ERRORS[name]}\n")
        return None


resume_mod = _safe_import("resume")        # Member 2
scoring_mod = _safe_import("scoring")      # Member 2
interview_mod = _safe_import("interview")  # Member 3


def _warn(where, exc):
    print(f"\n[main] {where} failed -> {type(exc).__name__}: {exc}")
    if isinstance(exc, TypeError):
        print("[main] This usually means the function signature differs from the build plan. Check the adapter in main.py.")
    traceback.print_exc()
    print()


# ------------------------------------------------------------------ app setup
WHISPER_STATE = {"status": "not loaded"}  # not loaded | loading | ready | failed


def _warm_whisper():
    """Load Whisper in the background so the first spoken answer is not slow."""
    if not (interview_mod and hasattr(interview_mod, "whisper_ready")):
        WHISPER_STATE["status"] = "failed"
        return
    WHISPER_STATE["status"] = "loading"
    ok = interview_mod.whisper_ready()
    WHISPER_STATE["status"] = "ready" if ok else "failed"
    print(f"[main] Whisper speech model: {WHISPER_STATE['status']}")


@asynccontextmanager
async def lifespan(_app):
    db.init_db()
    threading.Thread(target=_warm_whisper, name="whisper-warmup", daemon=True).start()
    print("[main] CareerLens backend ready on http://localhost:8000  (docs: /docs)")
    if IMPORT_ERRORS:
        print(f"[main] Modules with problems: {list(IMPORT_ERRORS)}")
    yield
    shield.monitor.stop_session()


app = FastAPI(title="CareerLens API", version="1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

RESUMES = {}   # resume_id -> analysis result
SESSIONS = {}  # session_id -> interview state


# ------------------------------------------------------------------ adapters (Member 2 / Member 3)
def adapt_analyze_resume(pdf_bytes, role, jd_text):
    """Member 2: resume.analyze_resume(pdf_bytes, role, jd_text) -> resume shape"""
    result = None
    if resume_mod and hasattr(resume_mod, "analyze_resume"):
        try:
            result = resume_mod.analyze_resume(pdf_bytes, role, jd_text)
        except Exception as exc:  # noqa: BLE001
            _warn("resume.analyze_resume", exc)
    if not isinstance(result, dict):
        raise HTTPException(status_code=500, detail="Resume analysis failed. Check the backend terminal for the error.")

    result.setdefault("parsed", {})
    result.setdefault("ats_score", 0)
    result.setdefault("ats_checks", [])
    result.setdefault("keywords", {"matched": [], "missing": []})
    result.setdefault("feedback", {"strengths": [], "weaknesses": [], "rewrites": []})
    return result


def _normalise_question(q, index, total):
    if isinstance(q, str):
        q = {"text": q}
    q = dict(q)
    q.setdefault("id", f"q{index}")
    q.setdefault("type", "technical")
    q.setdefault("text", "")
    q["index"] = index
    q["total"] = total
    return q


FALLBACK_QUESTIONS = [
    {"type": "intro", "text": "Tell me about yourself and why you are interested in this role."},
    {"type": "claim_probe", "text": "Pick the project on your resume you are proudest of. What exactly did you build, and how did you measure its success?"},
    {"type": "claim_probe", "text": "Choose one skill listed on your resume. Describe a specific time you used it and what the result was."},
    {"type": "technical", "text": "Explain a technical concept from your target role to someone who has never heard of it."},
    {"type": "behavioural", "text": "Tell me about a time you faced a difficult problem in a team. Use the situation, task, action, result format."},
]


def adapt_start_plan(parsed_resume, role):
    """Member 3: interview.start_plan(parsed_resume, role) -> list of questions"""
    questions = None
    if interview_mod and hasattr(interview_mod, "start_plan"):
        try:
            questions = interview_mod.start_plan(parsed_resume, role)
        except Exception as exc:  # noqa: BLE001
            _warn("interview.start_plan", exc)
    if isinstance(questions, dict):
        questions = questions.get("questions")
    if not isinstance(questions, list) or not questions:
        print("[main] Using fallback questions.")
        questions = FALLBACK_QUESTIONS
    total = len(questions)
    return [_normalise_question(q, i + 1, total) for i, q in enumerate(questions)]


def adapt_transcribe(audio_path):
    """Member 3: interview.transcribe(audio_path) -> (transcript, speech, error_code, detail)"""
    if not (interview_mod and hasattr(interview_mod, "transcribe")):
        return "", None, "model_not_loaded", "interview.py could not be imported"
    try:
        result = interview_mod.transcribe(audio_path)
    except Exception as exc:  # noqa: BLE001
        _warn("interview.transcribe", exc)
        return "", None, "error", str(exc)

    if isinstance(result, str):
        return result.strip(), None, ("" if result.strip() else "no_speech"), ""
    if not isinstance(result, dict):
        return "", None, "error", "transcribe returned an unexpected value"

    transcript = (result.get("transcript") or result.get("text") or "").strip()
    speech = result.get("speech")
    if not isinstance(speech, dict):
        keys = ("wpm", "filler_count", "long_pauses", "duration_s")
        speech = {k: result[k] for k in keys if k in result} or None
    error = "" if transcript else (result.get("error") or "no_speech")
    return transcript, speech, error, result.get("detail", "")


VOICE_ERRORS = {
    "model_not_loaded": "The speech model is not ready. Check the backend terminal for a Whisper message, or type your answer.",
    "too_short": "The recording was empty or too short. Record again and speak for at least 5 seconds.",
    "decode_failed": "The recording could not be read. Record again, or type your answer.",
    "no_speech": "No speech was heard in the recording. Check that the right microphone is selected, speak closer, or type your answer.",
    "error": "Something went wrong while transcribing. Record again, or type your answer.",
}


def adapt_evaluate(question, transcript):
    """Member 3: interview.evaluate_answer(question, transcript) -> evaluation dict"""
    evaluation = None
    if interview_mod and hasattr(interview_mod, "evaluate_answer"):
        try:
            evaluation = interview_mod.evaluate_answer(question, transcript)
        except Exception as exc:  # noqa: BLE001
            _warn("interview.evaluate_answer", exc)
    if not isinstance(evaluation, dict) or "error" in evaluation:
        evaluation = {
            "score": None,
            "clarity": None,
            "strengths": [],
            "missing_points": [],
            "better_answer": "",
            "note": "AI feedback was not available for this answer.",
        }
    evaluation.setdefault("strengths", [])
    evaluation.setdefault("missing_points", [])
    evaluation.setdefault("better_answer", "")
    return evaluation


def _answers_for_scoring(answers):
    """scoring.py reads the question type from answer["question"]["type"]."""
    shaped = []
    for a in answers:
        item = dict(a)
        item["question"] = {"id": a.get("question_id"), "type": a.get("type"), "text": a.get("question")}
        item["question_type"] = a.get("type")
        shaped.append(item)
    return shaped


def adapt_final_scores(session):
    """Member 2: scoring.final_scores(session_data) -> {scores, score_notes}"""
    session_data = {"role": session["role"], "resume": session["resume"], "answers": _answers_for_scoring(session["answers"])}
    if scoring_mod and hasattr(scoring_mod, "final_scores"):
        try:
            result = scoring_mod.final_scores(session_data)
            if isinstance(result, dict):
                if "scores" in result:
                    result.setdefault("score_notes", {})
                    return result
                if "communication" in result:
                    return {"scores": result, "score_notes": {}}
        except Exception as exc:  # noqa: BLE001
            _warn("scoring.final_scores", exc)
    print("[main] Using fallback scoring.")
    return fallback_scores(session["resume"], session["answers"])


def adapt_weak_answers(answers):
    """Member 2: scoring.select_weak_answers(answers) -> answers with score <= 5"""
    shaped = _answers_for_scoring(answers)
    if scoring_mod and hasattr(scoring_mod, "select_weak_answers"):
        try:
            return scoring_mod.select_weak_answers(shaped)
        except Exception as exc:  # noqa: BLE001
            _warn("scoring.select_weak_answers", exc)
    return [a for a in shaped if isinstance((a.get("evaluation") or {}).get("score"), (int, float)) and a["evaluation"]["score"] <= 5]


def adapt_build_roadmap(missing_keywords, weak_answers):
    """Member 2: scoring.build_roadmap(missing_keywords, weak_answers) -> roadmap list"""
    if scoring_mod and hasattr(scoring_mod, "build_roadmap"):
        try:
            result = scoring_mod.build_roadmap(missing_keywords, weak_answers)
            if isinstance(result, dict):
                result = result.get("roadmap")
            if isinstance(result, list):
                return result
        except Exception as exc:  # noqa: BLE001
            _warn("scoring.build_roadmap", exc)
    return [{"skill": k, "why": "Missing keyword for your target role", "resources": [], "days": ""} for k in missing_keywords[:5]]


# ------------------------------------------------------------------ fallback scoring (Section 7 formulas)
def _avg(values):
    values = [v for v in values if isinstance(v, (int, float))]
    return sum(values) / len(values) if values else None


def _delivery_score(speech):
    """100 minus penalties for pace, fillers and long pauses (voice answers only)."""
    score = 100
    wpm = speech.get("wpm")
    if isinstance(wpm, (int, float)) and not 110 <= wpm <= 170:
        score -= 15
    minutes = max((speech.get("duration_s") or 0) / 60, 0.1)
    fillers_per_min = (speech.get("filler_count") or 0) / minutes
    if fillers_per_min > 3:
        score -= 5 * int(fillers_per_min - 3)
    score -= 5 * (speech.get("long_pauses") or 0)
    return max(0, min(100, score))


def fallback_scores(resume_result, answers):
    evaluations = [a.get("evaluation") or {} for a in answers]
    clarity = _avg([e.get("clarity") for e in evaluations])
    voice = [a["speech"] for a in answers if a.get("speech")]
    delivery = _avg([_delivery_score(s) for s in voice])

    if clarity is None and delivery is None:
        communication, comm_note = None, "not measured"
    elif delivery is None:
        communication, comm_note = clarity * 10, "text-based"
    elif clarity is None:
        communication, comm_note = delivery, "voice only"
    else:
        communication, comm_note = 0.6 * clarity * 10 + 0.4 * delivery, "measured"

    eye = gaze_mod.average_eye_contact(answers)
    fluency = delivery
    if eye is not None and fluency is not None:
        confidence, conf_note = 0.6 * eye + 0.4 * fluency, "measured"
    elif eye is not None:
        confidence, conf_note = eye, "webcam only"
    elif fluency is not None:
        confidence, conf_note = fluency, "voice only"
    else:
        confidence, conf_note = None, "not measured"

    tech_answers = [a for a in answers if a.get("type") in ("claim_probe", "technical")] or answers
    tech = _avg([(a.get("evaluation") or {}).get("score") for a in tech_answers])
    technical = tech * 10 if tech is not None else None

    ats = resume_result.get("ats_score") or 0
    kw = resume_result.get("keywords") or {}
    matched, missing = len(kw.get("matched", [])), len(kw.get("missing", []))
    kw_pct = (matched / (matched + missing) * 100) if (matched + missing) else 0
    resume_score = 0.6 * ats + 0.4 * kw_pct

    def r(x):
        return None if x is None else round(x)

    return {
        "scores": {"communication": r(communication), "confidence": r(confidence), "technical": r(technical), "resume": r(resume_score)},
        "score_notes": {"communication": comm_note, "confidence": conf_note},
    }


# ------------------------------------------------------------------ request bodies
class StartRequest(BaseModel):
    resume_id: str
    role: str
    consent: bool = False


class FinishRequest(BaseModel):
    session_id: str


# ------------------------------------------------------------------ routes
@app.get("/api/health")
def health():
    return {
        "ollama": llm.is_ollama_up(),
        "whisper": WHISPER_STATE["status"] == "ready",
        "whisper_status": WHISPER_STATE["status"],
        "shield": "available" if shield.AVAILABLE else "unavailable",
        "modules": {**{name: "ok" for name in ("resume", "scoring", "interview")}, **IMPORT_ERRORS},
    }


@app.post("/api/resume/analyze")
def analyze_resume(file: UploadFile = File(...), role: str = Form(...), jd_text: str = Form("")):
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload your resume as a PDF file.")
    pdf_bytes = file.file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")

    result = adapt_analyze_resume(pdf_bytes, role, jd_text or "")
    resume_id = result.get("resume_id") or f"r_{uuid.uuid4().hex[:8]}"
    result["resume_id"] = resume_id
    result["role"] = role
    RESUMES[resume_id] = result
    return result


@app.post("/api/interview/start")
def interview_start(body: StartRequest):
    resume_result = RESUMES.get(body.resume_id)
    if not resume_result:
        raise HTTPException(status_code=404, detail="Resume not found. Upload your resume again.")

    questions = adapt_start_plan(resume_result.get("parsed", {}), body.role)
    session_id = f"s_{uuid.uuid4().hex[:8]}"
    SESSIONS[session_id] = {
        "session_id": session_id,
        "role": body.role,
        "resume_id": body.resume_id,
        "resume": resume_result,
        "questions": questions,
        "answers": [],
    }
    shield.monitor.start_session(session_id, body.consent)
    return {"session_id": session_id, "question": _public_question(questions[0])}


def _public_question(q):
    """Send only what the browser needs (hide expected key points)."""
    return {k: q[k] for k in ("id", "index", "total", "type", "text") if k in q}


@app.post("/api/interview/answer")
def interview_answer(
    session_id: str = Form(...),
    question_id: str = Form(...),
    typed_text: str = Form(None),
    audio: UploadFile = File(None),
    gaze: str = Form(None),
):
    session = SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Interview session not found. Start a new interview.")

    questions = session["questions"]
    position = next((i for i, q in enumerate(questions) if q["id"] == question_id), None)
    if position is None:
        raise HTTPException(status_code=400, detail="Unknown question id.")
    question = questions[position]

    transcript, speech, input_mode = "", None, "typed"
    voice_error, voice_detail = "", ""
    if audio is not None and audio.filename:
        extension = os.path.splitext(audio.filename)[1] or ".webm"
        audio_path = os.path.join(AUDIO_DIR, f"{session_id}_{question_id}{extension}")
        try:
            with open(audio_path, "wb") as f:
                f.write(audio.file.read())
            size = os.path.getsize(audio_path)
            transcript, speech, voice_error, voice_detail = adapt_transcribe(audio_path)
            input_mode = "voice"
            if voice_error:
                # keep ONE copy of the last failed recording so it can be checked with check_audio.py
                failed_copy = os.path.join(AUDIO_DIR, f"last_failed{extension}")
                shutil.copyfile(audio_path, failed_copy)
                print(f"[main] Voice answer failed: {voice_error} ({size} bytes) {voice_detail}")
                print(f"[main] Saved a copy for checking: {failed_copy}  ->  python check_audio.py")
        finally:
            if os.path.exists(audio_path):
                os.remove(audio_path)  # privacy: audio is deleted right after transcription

    if not transcript and typed_text and typed_text.strip():
        transcript, speech, input_mode = typed_text.strip(), None, "typed"
    if not transcript:
        message = VOICE_ERRORS.get(voice_error) if voice_error else "No answer was received. Type your answer, or record it."
        raise HTTPException(status_code=400, detail=message or VOICE_ERRORS["error"])

    gaze_data = gaze_mod.summarise_gaze(gaze)
    evaluation = adapt_evaluate(question, transcript)

    answer = {
        "question_id": question_id,
        "question": question["text"],
        "type": question["type"],
        "transcript": transcript,
        "input_mode": input_mode,
        "speech": speech,
        "gaze": gaze_data,
        "evaluation": evaluation,
    }
    # replace an earlier answer to the same question (re-record), otherwise append
    session["answers"] = [a for a in session["answers"] if a["question_id"] != question_id] + [answer]

    next_question = questions[position + 1] if position + 1 < len(questions) else None
    return {
        "transcript": transcript,
        "input_mode": input_mode,
        "speech": speech,
        "gaze": gaze_data,
        "evaluation": evaluation,
        "next_question": _public_question(next_question) if next_question else None,
    }


@app.post("/api/interview/finish")
def interview_finish(body: FinishRequest):
    session = SESSIONS.get(body.session_id)
    if not session:
        saved = db.get_report(body.session_id)
        if saved:
            return saved
        raise HTTPException(status_code=404, detail="Interview session not found.")

    scored = adapt_final_scores(session)
    missing = (session["resume"].get("keywords") or {}).get("missing", [])
    roadmap = adapt_build_roadmap(missing, adapt_weak_answers(session["answers"]))

    integrity = shield.monitor.stop_session() if shield.monitor.session_id == body.session_id else {
        "status": "unavailable", "events": [], "reason": "Integrity check was not running for this session"}

    report = {
        "session_id": body.session_id,
        "role": session["role"],
        "scores": scored.get("scores", {}),
        "score_notes": scored.get("score_notes", {}),
        "answers": [
            {k: a.get(k) for k in ("question", "type", "transcript", "input_mode", "speech", "gaze", "evaluation")}
            for a in session["answers"]
        ],
        "roadmap": roadmap,
        "integrity": integrity,
    }
    db.save_report(body.session_id, session["role"], report)
    SESSIONS.pop(body.session_id, None)
    return report


@app.get("/api/shield/status")
def shield_status():
    return shield.monitor.status()


@app.get("/api/history")
def history():
    return db.list_history()


@app.get("/api/report/{session_id}")
def report(session_id: str):
    saved = db.get_report(session_id)
    if not saved:
        raise HTTPException(status_code=404, detail="Report not found.")
    return saved
