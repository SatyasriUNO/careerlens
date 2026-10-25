"""CareerLens - Member 2: final scores (PDF Section 7) and learning roadmap.

Public functions
----------------
final_scores(session_data, include_breakdown=False) -> {"scores": {...}, "score_notes": {...}}
build_roadmap(missing_keywords, weak_answers)        -> [{"skill", "why", "resources", "days"}]
select_weak_answers(answers)                         -> helper for Member 5 (weak = score <= 5)

session_data (contract proposed by Member 2, built by Member 5 at /api/interview/finish)::

    {"role": "SDE",
     "resume": {"ats_score": 72, "keywords": {"matched": [...], "missing": [...]}},
     "answers": [{"question": {"id": "q1", "type": "intro|claim_probe|technical|behavioural"},
                  "input_mode": "voice" | "typed",
                  "speech": {"wpm", "filler_count", "long_pauses", "duration_s"} | null,
                  "gaze":   {"eye_contact_pct", "look_away_count", "face_present_pct",
                             "tracking_quality": "good" | "low"} | null,
                  "evaluation": {"score": 1-10, "clarity": 1-10, ...} | null}]}

"Not measured": the score is ``None`` (JSON null) and ``score_notes[name] == "not measured"``.
Notes are "measured" | "not measured", plus "text-based" for Communication in typed-only sessions.
Neither function raises; every problem degrades to "not measured" / empty list and is logged.
"""

from __future__ import annotations

import json
import logging
import math
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from resume import first_term_index, normalize_text

logger = logging.getLogger("careerlens.scoring")

DATA_DIR = Path(__file__).resolve().parent / "data"

# ---- Section 7 constants (exact values from the PDF) ----------------------
WPM_MIN, WPM_MAX = 110, 170          # delivery: -15 if WPM outside this range
WPM_PENALTY = 15
FILLER_FREE_PER_MIN = 3              # -5 per filler per minute ABOVE 3
FILLER_PENALTY = 5
PAUSE_PENALTY = 5                    # -5 per long pause (> 2 s, counted by Member 3)
W_CLARITY, W_DELIVERY = 0.60, 0.40   # Communication (voice)
W_EYE, W_FLUENCY = 0.60, 0.40        # Confidence
W_ATS, W_KEYWORD = 0.60, 0.40        # Resume
TECHNICAL_TYPES = ("claim_probe", "technical")

# ---- Implementation decisions (not in the PDF) ----------------------------
WEAK_ANSWER_MAX_SCORE = 5
MAX_ROADMAP_ITEMS = 8

MEASURED, NOT_MEASURED, TEXT_BASED = "measured", "not measured", "text-based"
SCORE_NAMES = ("communication", "confidence", "technical", "resume")


# --------------------------------------------------------------------------
# Small safe helpers
# --------------------------------------------------------------------------
def _num(value: Any) -> Optional[float]:
    """A real finite number or None (rejects bool, str, NaN, inf, None)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _round_score(value: float) -> int:
    return int(math.floor(_clamp(value, 0, 100) + 0.5))


def _mean(values: list[float]) -> Optional[float]:
    return sum(values) / len(values) if values else None


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _answers(session: dict) -> list[dict]:
    raw = session.get("answers")
    return [a for a in raw if isinstance(a, dict)] if isinstance(raw, list) else []


def _answer_type(answer: dict) -> str:
    question = answer.get("question")
    if isinstance(question, dict):
        return str(question.get("type") or "")
    return str(answer.get("question_type") or "")


def _evaluation_value(answer: dict, key: str) -> Optional[float]:
    """evaluation.score / evaluation.clarity, clamped to the 0-10 range the LLM is asked for."""
    value = _num(_dict(answer.get("evaluation")).get(key))
    return None if value is None else _clamp(value, 0, 10)


def _voice_metrics(answer: dict) -> Optional[dict[str, float]]:
    """Usable speech numbers, or None. duration_s must be > 0 (fillers are counted per minute)."""
    if answer.get("input_mode") == "typed":
        return None
    speech = answer.get("speech")
    if not isinstance(speech, dict):
        return None
    wpm, fillers = _num(speech.get("wpm")), _num(speech.get("filler_count"))
    pauses, duration = _num(speech.get("long_pauses")), _num(speech.get("duration_s"))
    if None in (wpm, fillers, pauses, duration) or duration <= 0:
        return None
    return {"wpm": wpm, "fillers": max(0.0, fillers), "pauses": max(0.0, pauses), "duration": duration}


# --------------------------------------------------------------------------
# Section 7 building blocks
# --------------------------------------------------------------------------
def _filler_pause_penalty(m: dict[str, float]) -> float:
    fillers_per_minute = m["fillers"] / (m["duration"] / 60.0)
    return FILLER_PENALTY * max(0.0, fillers_per_minute - FILLER_FREE_PER_MIN) + PAUSE_PENALTY * m["pauses"]


def _delivery(m: dict[str, float]) -> float:
    """Delivery: 100, -15 if WPM outside 110-170, filler and pause penalties."""
    wpm_penalty = WPM_PENALTY if (m["wpm"] < WPM_MIN or m["wpm"] > WPM_MAX) else 0
    return max(0.0, 100.0 - wpm_penalty - _filler_pause_penalty(m))


def _fluency(m: dict[str, float]) -> float:
    """Fluency: 100 minus filler and pause penalties only (no WPM term)."""
    return max(0.0, 100.0 - _filler_pause_penalty(m))


def _communication(answers: list[dict]) -> tuple[Optional[float], str, dict]:
    voice = [(a, m) for a in answers if (m := _voice_metrics(a)) is not None]
    voice_clarity = [c * 10 for a, _ in voice if (c := _evaluation_value(a, "clarity")) is not None]
    if voice_clarity:  # voice formula: 60% clarity + 40% delivery (voice answers only)
        clarity_avg = _mean(voice_clarity)
        delivery_avg = _mean([_delivery(m) for _, m in voice])
        value = W_CLARITY * clarity_avg + W_DELIVERY * delivery_avg
        return value, MEASURED, {"mode": "voice", "clarity": clarity_avg, "delivery": delivery_avg,
                                 "voice_answers": len(voice)}
    all_clarity = [c * 10 for a in answers if (c := _evaluation_value(a, "clarity")) is not None]
    if all_clarity:  # typed only: 100% clarity
        clarity_avg = _mean(all_clarity)
        return clarity_avg, TEXT_BASED, {"mode": "text", "clarity": clarity_avg}
    return None, NOT_MEASURED, {"mode": None}


def _confidence(answers: list[dict]) -> tuple[Optional[float], str, dict]:
    eye_values = []
    for a in answers:
        gaze = _dict(a.get("gaze"))
        eye = _num(gaze.get("eye_contact_pct"))
        if gaze.get("tracking_quality") == "good" and eye is not None:
            eye_values.append(_clamp(eye, 0, 100))
    voice_metrics = [m for a in answers if (m := _voice_metrics(a)) is not None]
    eye_avg = _mean(eye_values)
    fluency_avg = _mean([_fluency(m) for m in voice_metrics])
    detail = {"eye_contact": eye_avg, "fluency": fluency_avg}
    if eye_avg is not None and fluency_avg is not None:
        return W_EYE * eye_avg + W_FLUENCY * fluency_avg, MEASURED, detail
    if eye_avg is not None:
        return eye_avg, MEASURED, detail
    if fluency_avg is not None:
        return fluency_avg, MEASURED, detail
    return None, NOT_MEASURED, detail


def _technical(answers: list[dict]) -> tuple[Optional[float], str, dict]:
    values = [s * 10 for a in answers if _answer_type(a) in TECHNICAL_TYPES
              and (s := _evaluation_value(a, "score")) is not None]
    if not values:
        return None, NOT_MEASURED, {"answers_used": 0}
    return _mean(values), MEASURED, {"answers_used": len(values)}


def _resume(session: dict) -> tuple[Optional[float], str, dict]:
    resume = _dict(session.get("resume"))
    ats = _num(resume.get("ats_score"))
    ats = None if ats is None else _clamp(ats, 0, 100)
    keywords = _dict(resume.get("keywords"))
    matched, missing = keywords.get("matched"), keywords.get("missing")
    matched_n = len(matched) if isinstance(matched, list) else 0
    missing_n = len(missing) if isinstance(missing, list) else 0
    keyword_pct = 100.0 * matched_n / (matched_n + missing_n) if (matched_n + missing_n) > 0 else None
    detail = {"ats": ats, "keyword_match_pct": keyword_pct}
    if ats is not None and keyword_pct is not None:
        return W_ATS * ats + W_KEYWORD * keyword_pct, MEASURED, detail
    if ats is not None:
        return ats, MEASURED, detail
    if keyword_pct is not None:
        return keyword_pct, MEASURED, detail
    return None, NOT_MEASURED, detail


# --------------------------------------------------------------------------
# Public: final_scores
# --------------------------------------------------------------------------
def final_scores(session_data: Any, include_breakdown: bool = False) -> dict[str, Any]:
    """Compute the four scores. Returns {"scores", "score_notes"} (+ "breakdown" if requested)."""
    try:
        session = _dict(session_data)
        answers = _answers(session)
        parts = {"communication": _communication(answers), "confidence": _confidence(answers),
                 "technical": _technical(answers), "resume": _resume(session)}
    except Exception:
        logger.exception("final_scores failed unexpectedly; returning 'not measured'")
        parts = {name: (None, NOT_MEASURED, {}) for name in SCORE_NAMES}

    result: dict[str, Any] = {
        "scores": {name: (None if parts[name][0] is None else _round_score(parts[name][0]))
                   for name in SCORE_NAMES},
        "score_notes": {name: parts[name][1] for name in SCORE_NAMES},
    }
    if include_breakdown:
        result["breakdown"] = {name: parts[name][2] for name in SCORE_NAMES}
    return result


def select_weak_answers(answers: Any, max_score: float = WEAK_ANSWER_MAX_SCORE) -> list[dict]:
    """Answers whose evaluation.score is a number <= ``max_score`` (helper for Member 5)."""
    if not isinstance(answers, list):
        return []
    weak = []
    for answer in answers:
        if isinstance(answer, dict):
            score = _num(_dict(answer.get("evaluation")).get("score"))
            if score is not None and score <= max_score:
                weak.append(answer)
    return weak


# --------------------------------------------------------------------------
# Roadmap (only resources from data/resources.json)
# --------------------------------------------------------------------------
@lru_cache(maxsize=1)
def load_resources() -> dict[str, dict[str, Any]]:
    """Read and validate data/resources.json. Invalid entries are dropped and logged. {} on failure."""
    path = DATA_DIR / "resources.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))["skills"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        logger.error("Cannot load %s: %s", path, exc)
        return {}
    skills: dict[str, dict[str, Any]] = {}
    for skill_id, skill in raw.items():
        if not isinstance(skill, dict) or not isinstance(skill.get("display"), str):
            logger.error("resources.json: skill %r malformed, skipped", skill_id)
            continue
        links = [{"title": r["title"], "url": r["url"]} for r in skill.get("resources", [])
                 if isinstance(r, dict) and isinstance(r.get("title"), str)
                 and isinstance(r.get("url"), str) and r["url"].startswith("https://")]
        if not links:
            logger.error("resources.json: skill %r has no valid links, skipped", skill_id)
            continue
        aliases = [a for a in skill.get("aliases", []) if isinstance(a, str)]
        skills[skill_id] = {"display": skill["display"], "days": str(skill.get("days", "")),
                            "aliases": aliases, "resources": links}
    return skills


@lru_cache(maxsize=1)
def _alias_index() -> dict[str, str]:
    """normalized alias -> skill id (first skill wins on a clash)."""
    index: dict[str, str] = {}
    for skill_id, skill in load_resources().items():
        for alias in [skill_id, skill["display"], *skill["aliases"]]:
            index.setdefault(normalize_text(alias), skill_id)
    return index


def _weak_answer_text(item: Any) -> str:
    """Question text + missing points of a weak answer (strings are used as they are)."""
    if isinstance(item, str):
        return item
    if not isinstance(item, dict):
        return ""
    question = item.get("question")
    parts = [question.get("text", "") if isinstance(question, dict) else question]
    evaluation = _dict(item.get("evaluation"))
    points = evaluation.get("missing_points")
    if isinstance(points, list):
        parts.extend(points)
    return " ".join(p for p in parts if isinstance(p, str))


def _skills_from_text(text: str) -> list[str]:
    """Skill ids mentioned in free text, ordered by first mention. Single-letter aliases are ignored."""
    norm = normalize_text(text)
    if not norm:
        return []
    found: dict[str, int] = {}
    for alias, skill_id in _alias_index().items():
        if len(alias) < 2:
            continue
        pos = first_term_index(norm, alias)
        if pos >= 0:
            found[skill_id] = min(pos, found.get(skill_id, pos))
    return sorted(found, key=lambda s: (found[s], s))


def build_roadmap(missing_keywords: Any, weak_answers: Any, max_items: int = MAX_ROADMAP_ITEMS) -> list[dict[str, Any]]:
    """Learning roadmap from missing keywords and weak answers. [] for empty input. Never raises.

    Item: {"skill": display name, "why": str, "resources": [{"title","url"}], "days": "1-3"}.
    Order: skills that are both a missing keyword and a weak topic first, then the remaining
    missing keywords (input order), then weak-answer topics (order of mention).
    """
    try:
        index = _alias_index()
        from_keywords: list[str] = []
        for kw in missing_keywords if isinstance(missing_keywords, (list, tuple)) else []:
            skill_id = index.get(normalize_text(kw)) if isinstance(kw, str) else None
            if skill_id and skill_id not in from_keywords:
                from_keywords.append(skill_id)

        from_answers: list[str] = []
        for item in weak_answers if isinstance(weak_answers, (list, tuple)) else []:
            for skill_id in _skills_from_text(_weak_answer_text(item)):
                if skill_id not in from_answers:
                    from_answers.append(skill_id)

        both = [s for s in from_keywords if s in from_answers]
        ordered = both + [s for s in from_keywords if s not in both] + [s for s in from_answers if s not in both]

        resources = load_resources()
        roadmap = []
        for skill_id in ordered[: max(0, int(max_items))]:
            skill = resources[skill_id]
            if skill_id in both:
                why = "Missing keyword for role and weak interview answer"
            elif skill_id in from_keywords:
                why = "Missing keyword for role"
            else:
                why = "Weak interview answer on this topic"
            roadmap.append({"skill": skill["display"], "why": why,
                            "resources": [dict(r) for r in skill["resources"]], "days": skill["days"]})
        return roadmap
    except Exception:
        logger.exception("build_roadmap failed unexpectedly; returning empty roadmap")
        return []
