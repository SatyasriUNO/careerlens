"""
gaze.py  —  Member 4 (GazeGuard-lite, backend side)

The browser measures eye contact with MediaPipe and sends only numbers.
This file checks those numbers, cleans them, and summarises them.

Functions used by main.py / scoring.py:
    summarise_gaze(raw)          -> one answer's gaze dict, or None
    average_eye_contact(answers) -> average eye-contact % over good answers, or None

Run a self-test:
    python gaze.py
"""

import json

VALID_QUALITY = ("good", "low")


def _num(value, low, high, default=None):
    """Turn value into a number clamped between low and high. Returns default if impossible."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number:  # NaN check
        return default
    return max(low, min(high, number))


def summarise_gaze(raw):
    """
    raw: the 'gaze' form field from the browser. Can be a JSON string, a dict, or None.
    Returns a clean dict in the contract shape, or None if there is no usable gaze data.

    Contract shape:
    {"eye_contact_pct": 71, "look_away_count": 3, "face_present_pct": 98,
     "tracking_quality": "good" | "low", "duration_s": 52.4}
    """
    if raw is None or raw == "" or raw == "null":
        return None

    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return None

    if not isinstance(raw, dict):
        return None

    eye = _num(raw.get("eye_contact_pct"), 0, 100)
    face = _num(raw.get("face_present_pct"), 0, 100)
    if eye is None or face is None:
        return None

    look_aways = int(_num(raw.get("look_away_count"), 0, 1000, 0))
    duration = _num(raw.get("duration_s"), 0, 3600, 0.0)

    quality = raw.get("tracking_quality")
    if quality not in VALID_QUALITY:
        quality = "low"
    # Extra safety: very short answers or a mostly missing face are never "good"
    if face < 80 or duration < 3:
        quality = "low"

    return {
        "eye_contact_pct": round(eye),
        "look_away_count": look_aways,
        "face_present_pct": round(face),
        "tracking_quality": quality,
        "duration_s": round(duration, 1),
    }


def average_eye_contact(answers):
    """
    answers: list of answer dicts that may contain a "gaze" key.
    Uses only answers whose tracking_quality is "good".
    Returns the average eye-contact % (0-100), or None if nothing was measured well.
    """
    values = []
    for answer in answers or []:
        gaze = answer.get("gaze") if isinstance(answer, dict) else None
        if gaze and gaze.get("tracking_quality") == "good":
            values.append(gaze["eye_contact_pct"])
    if not values:
        return None
    return round(sum(values) / len(values))


if __name__ == "__main__":
    good = '{"eye_contact_pct": 71.4, "look_away_count": 3, "face_present_pct": 97.2, "tracking_quality": "good", "duration_s": 48.2}'
    bad_face = {"eye_contact_pct": 90, "look_away_count": 0, "face_present_pct": 40, "tracking_quality": "good", "duration_s": 30}
    broken = "not json"

    print("good    ->", summarise_gaze(good))
    print("bad_face->", summarise_gaze(bad_face))
    print("broken  ->", summarise_gaze(broken))
    print("none    ->", summarise_gaze(None))
    sample = [{"gaze": summarise_gaze(good)}, {"gaze": summarise_gaze(bad_face)}, {"gaze": None}]
    print("average ->", average_eye_contact(sample))
