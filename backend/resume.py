"""CareerLens - Member 2: resume analysis (PDF -> sections -> ATS -> keywords -> feedback).

Public function
---------------
analyze_resume(pdf_bytes, role, jd_text="", llm=None) -> dict

Returned shape (PDF Section 6.1, POST /api/resume/analyze). ``resume_id`` is added
by Member 5 in main.py, not here::

    {"parsed":     {"name", "skills", "projects", "experience", "education"},
     "ats_score":  int 0-100,
     "ats_checks": [{"name", "passed", "tip"}, ...],      # 10 checks, fixed order
     "keywords":   {"matched": [...], "missing": [...]},
     "feedback":   {"strengths": [...], "weaknesses": [...],
                    "rewrites": [{"original", "improved"}, ...]}}

Rules
-----
* ATS score, checks and keyword match are fully deterministic (no LLM).
* Exactly ONE LLM call (JSON mode) produces strengths / weaknesses / 3 rewrites.
* The function never raises. Bad PDF, empty text, LLM failure -> same shape, safe
  fallback feedback, errors are logged (logger "careerlens.resume").

Command line::

    python resume.py sample.pdf [role] [jd.txt]      # prints the JSON result
"""

from __future__ import annotations

import json
import logging
import re
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Optional

try:  # PyMuPDF >= 1.24 exposes "pymupdf"; older versions only "fitz".
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    try:
        import fitz  # type: ignore
    except ImportError:
        fitz = None  # extraction will report "pymupdf_not_installed"

logger = logging.getLogger("careerlens.resume")

DATA_DIR = Path(__file__).resolve().parent / "data"

# --------------------------------------------------------------------------
# Tunable constants (implementation decisions, not in the PDF)
# --------------------------------------------------------------------------
MIN_TEXT_WORDS = 20            # fewer words than this = unreadable / scanned PDF
MIN_STANDARD_HEADINGS = 3      # of education/skills/projects/experience/certifications
MIN_BULLETS = 3
ACTION_VERB_RATIO = 0.60       # share of bullets that must start with an action verb
NUMBER_RATIO = 0.30            # share of bullets that must contain a digit
MAX_BULLET_WORDS = 35
CONTINUATION_MIN_PREV_LEN = 70  # a previous line this long is probably a wrapped line
JD_MIN_COUNT = 2               # a JD term must appear at least this often ...
JD_MAX_KEYWORDS = 10           # ... and at most this many are added
MAX_PROMPT_BULLETS = 12
MAX_PROMPT_BULLET_CHARS = 220
MAX_FEEDBACK_ITEMS = 5
MAX_FEEDBACK_CHARS = 300
REWRITE_COUNT = 3              # PDF: "3 bullet rewrites"

CORE_HEADINGS = ("education", "skills", "projects", "experience", "certifications")

SECTION_ALIASES: dict[str, list[str]] = {
    "education": ["education", "academic background", "academics", "educational qualification",
                  "educational qualifications", "academic qualifications", "academic details"],
    "skills": ["skills", "technical skills", "key skills", "core competencies", "technical proficiency",
               "skills and tools", "tools and technologies", "technologies", "technical expertise"],
    "projects": ["projects", "academic projects", "personal projects", "project work", "key projects",
                 "technical projects", "selected projects"],
    "experience": ["experience", "work experience", "professional experience", "internships",
                   "internship experience", "employment history", "work history", "internship"],
    "certifications": ["certifications", "certificates", "certification", "courses",
                       "licenses and certifications", "certifications and courses", "online courses"],
    "achievements": ["achievements", "awards", "honors", "honours", "accomplishments",
                     "awards and achievements", "awards and honors"],
    "publications": ["publications", "research papers", "papers", "research publications"],
    "summary": ["summary", "objective", "career objective", "profile", "professional summary", "about me"],
    "other": ["extracurricular", "extracurricular activities", "activities", "positions of responsibility",
              "hobbies", "interests", "languages", "volunteering", "leadership", "co curricular activities"],
}

# Past-tense / base-form action verbs accepted at the start of a bullet.
ACTION_VERBS = frozenset("""
accelerated achieved analysed analyzed applied architected assembled authored automated awarded boosted
built calibrated classified cleaned collaborated computed conducted configured constructed contributed
converted coordinated crafted created customised customized cut debugged delivered deployed designed
developed devised documented drove earned engineered enhanced established evaluated executed expanded
extracted fine-tuned finetuned forecasted formulated generated handled hosted implemented improved
increased initiated integrated interfaced investigated launched led leveraged maintained managed mentored
migrated modelled modeled monitored operated optimised optimized organized organised owned ported
predicted presented processed produced programmed prototyped published ranked reduced refactored
researched resolved redesigned revamped scaled secured shipped simulated spearheaded streamlined
supported tested trained tuned utilised utilized visualised visualized won wrote
""".split())

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"\+?\d[\d\s\-().]{8,18}\d")
_LINK_RE = re.compile(r"(github\.com|linkedin\.com)", re.IGNORECASE)
_BULLET_RE = re.compile(r"^\s*[•●▪◦‣·∙■\-–—*►▶]\s*")
_LONE_MARKER_RE = re.compile(r"^\s*[•●▪◦‣·∙■\-–—*►▶]\s*$")
_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z .'\-]{1,39}$")


# --------------------------------------------------------------------------
# Data loading
# --------------------------------------------------------------------------
def normalize_text(text: str) -> str:
    """Lowercase; '-' and '_' become spaces; whitespace collapsed. Used for all term matching."""
    text = (text or "").lower().replace("-", " ").replace("_", " ").replace("\u00a0", " ")
    return re.sub(r"\s+", " ", text).strip()


@lru_cache(maxsize=1)
def load_role_keywords() -> dict[str, list[str]]:
    """Read data/role_keywords.json -> {role: [normalized unique keywords]}. {} on failure."""
    path = DATA_DIR / "role_keywords.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.error("Cannot load %s: %s", path, exc)
        return {}
    result: dict[str, list[str]] = {}
    for role, words in raw.items():
        if not isinstance(words, list):
            logger.error("role_keywords.json: role %r is not a list", role)
            continue
        seen: list[str] = []
        for word in words:
            norm = normalize_text(word) if isinstance(word, str) else ""
            if norm and norm not in seen:
                seen.append(norm)
        result[role] = seen
    return result


def resolve_role(role: Any) -> Optional[str]:
    """Case-insensitive match of ``role`` to a key of role_keywords.json, else None."""
    if not isinstance(role, str):
        return None
    wanted = role.strip().lower()
    for key in load_role_keywords():
        if key.lower() == wanted:
            return key
    return None


# --------------------------------------------------------------------------
# Term matching (shared with scoring.py)
# --------------------------------------------------------------------------
@lru_cache(maxsize=4096)
def _term_regex(term: str) -> "re.Pattern[str]":
    variants = {term, term.replace(".", ""), term.replace(" ", ""), term.replace(".", " ")}
    alternation = "|".join(re.escape(v) for v in sorted(variants, key=len, reverse=True) if v)
    # Not glued to letters/digits/+/#, so "java" != "javascript", "c" != "c++", "sql" != "mysql".
    return re.compile(rf"(?<![a-z0-9+#])(?:{alternation})(?![a-z0-9+#])")


def count_term(normalized_text: str, term: str) -> int:
    """Number of whole-term occurrences of ``term`` in already-normalized text."""
    term = normalize_text(term)
    return len(_term_regex(term).findall(normalized_text)) if term else 0


def first_term_index(normalized_text: str, term: str) -> int:
    """Index of the first whole-term occurrence, or -1."""
    term = normalize_text(term)
    match = _term_regex(term).search(normalized_text) if term else None
    return match.start() if match else -1


# --------------------------------------------------------------------------
# A. PDF extraction
# --------------------------------------------------------------------------
def extract_pdf(pdf_bytes: Any) -> dict[str, Any]:
    """Return {"text", "pages", "links", "error"}. Never raises; ``error`` is None on success."""
    result: dict[str, Any] = {"text": "", "pages": 0, "links": [], "error": None}
    if not isinstance(pdf_bytes, (bytes, bytearray)) or len(pdf_bytes) == 0:
        result["error"] = "empty_input"
        return result
    if fitz is None:
        result["error"] = "pymupdf_not_installed"
        return result
    doc = None
    try:
        doc = fitz.open(stream=bytes(pdf_bytes), filetype="pdf")
        if doc.needs_pass:
            result["error"] = "encrypted_pdf"
            return result
        parts: list[str] = []
        for page in doc:
            parts.append(page.get_text("text"))
            for link in page.get_links():
                uri = link.get("uri")
                if uri:
                    result["links"].append(uri)
        result["text"] = "\n".join(parts)
        result["pages"] = doc.page_count
    except Exception as exc:  # malformed / corrupt PDFs raise various PyMuPDF errors
        logger.warning("PDF could not be read: %s", exc)
        result.update({"text": "", "pages": 0, "links": [], "error": f"unreadable_pdf: {exc}"})
    finally:
        if doc is not None:
            doc.close()
    return result


# --------------------------------------------------------------------------
# B. Section splitting and parsing
# --------------------------------------------------------------------------
def _heading_key(line: str) -> str:
    key = line.lower().replace("&", " and ")
    key = re.sub(r"[^a-z ]", " ", key)
    return re.sub(r"\s+", " ", key).strip()


_HEADING_LOOKUP: dict[str, str] = {
    _heading_key(alias): section for section, aliases in SECTION_ALIASES.items() for alias in aliases
}


def detect_heading(line: str) -> Optional[str]:
    """Return the section name if ``line`` is a recognised heading, else None."""
    stripped = line.strip()
    if not stripped or len(stripped) > 40 or len(stripped.split()) > 5:
        return None
    return _HEADING_LOOKUP.get(_heading_key(stripped))


def _clean_lines(text: str) -> list[str]:
    """Split into stripped lines; merge a lone bullet glyph with the line after it."""
    raw = [ln.replace("\u00a0", " ").strip() for ln in (text or "").replace("\r", "\n").split("\n")]
    merged: list[str] = []
    i = 0
    while i < len(raw):
        line = raw[i]
        if _LONE_MARKER_RE.match(line) and line and i + 1 < len(raw) and raw[i + 1]:
            merged.append("• " + raw[i + 1])
            i += 2
            continue
        merged.append(line)
        i += 1
    return merged


def split_sections(text: str) -> dict[str, list[str]]:
    """Split resume text by headings. Lines before the first heading go to "header"."""
    sections: dict[str, list[str]] = {"header": []}
    current = "header"
    for line in _clean_lines(text):
        if not line:
            continue
        heading = detect_heading(line)
        if heading:
            current = heading
            sections.setdefault(current, [])
        else:
            sections[current].append(line)
    return sections


def _is_continuation(line: str, prev_len: int) -> bool:
    return line[0].islower() or line[0].isdigit() or line[0] in ",;:)%" or prev_len >= CONTINUATION_MIN_PREV_LEN


def parse_entries(lines: list[str]) -> list[dict[str, Any]]:
    """Turn the lines of a Projects/Experience section into [{"title", "bullets"}]."""
    has_markers = any(_BULLET_RE.match(ln) for ln in lines)
    entries: list[dict[str, Any]] = []
    current: Optional[dict[str, Any]] = None
    open_bullet = False
    prev_len = 0

    def new_entry(title: str) -> dict[str, Any]:
        entry = {"title": title, "bullets": []}
        entries.append(entry)
        return entry

    for line in lines:
        if not line:
            continue
        marker = _BULLET_RE.match(line)
        if marker:
            text = line[marker.end():].strip()
            if current is None:
                current = new_entry("")
            if text:
                current["bullets"].append(text)
            open_bullet = bool(text)
        elif has_markers:
            if open_bullet and current is not None and _is_continuation(line, prev_len):
                current["bullets"][-1] += " " + line
            elif current is not None and not current["bullets"] and current["title"]:
                pass  # extra header line (dates / tech stack) before the bullets: ignore
            elif current is not None and not current["bullets"]:
                current["title"] = line
            else:
                current = new_entry(line)
                open_bullet = False
        else:  # section without bullet glyphs: long lines are bullets, short lines are titles
            if len(line.split()) > 6:
                if current is None:
                    current = new_entry("")
                current["bullets"].append(line)
            else:
                current = new_entry(line)
        prev_len = len(line)
    return [e for e in entries if e["title"] or e["bullets"]]


def parse_skills(lines: list[str]) -> list[str]:
    """Split the Skills section into unique individual skills (original casing kept)."""
    skills: list[str] = []
    seen: set[str] = set()
    for line in lines:
        line = _BULLET_RE.sub("", line).strip()
        if ":" in line:
            label, rest = line.split(":", 1)
            if len(label.split()) <= 4:
                line = rest
        line = line.replace("(", ",").replace(")", ",")
        for piece in re.split(r"[,;|•·]", line):
            skill = piece.strip(" .-\t")
            if 0 < len(skill) <= 40 and skill.lower() not in seen:
                seen.add(skill.lower())
                skills.append(skill)
    return skills


def _guess_name(header_lines: list[str]) -> str:
    for line in header_lines:
        lowered = line.lower()
        if "@" in line or "http" in lowered or "linkedin" in lowered or "github" in lowered:
            continue
        if _NAME_RE.match(line) and len(line.split()) <= 5:
            return line.strip()
    return ""


def merge_wrapped_lines(lines: list[str]) -> list[str]:
    """Join lines that are the wrapped continuation of the previous line (e.g. a long degree line)."""
    merged: list[str] = []
    prev_len = 0
    for line in lines:
        line = _BULLET_RE.sub("", line).strip()
        if not line:
            continue
        if merged and _is_continuation(line, prev_len):
            merged[-1] += " " + line
        else:
            merged.append(line)
        prev_len = len(line)
    return merged


def parse_resume(sections: dict[str, list[str]]) -> dict[str, Any]:
    """Build the ``parsed`` object of the API contract (exactly these five keys)."""
    return {
        "name": _guess_name(sections.get("header", [])),
        "skills": parse_skills(sections.get("skills", [])),
        "projects": parse_entries(sections.get("projects", [])),
        "experience": parse_entries(sections.get("experience", [])),
        "education": merge_wrapped_lines(sections.get("education", [])),
    }


# --------------------------------------------------------------------------
# C. ATS checks (10 deterministic rules)
# --------------------------------------------------------------------------
def find_email(text: str) -> bool:
    return bool(_EMAIL_RE.search(text or ""))


def find_phone(text: str) -> bool:
    for match in _PHONE_RE.finditer(text or ""):
        groups = re.findall(r"\d+", match.group())
        digits = sum(len(g) for g in groups)
        looks_like_years = all(len(g) == 4 and g[:2] in ("19", "20") for g in groups)
        if 10 <= digits <= 13 and not looks_like_years:
            return True
    return False


def _starts_with_action_verb(bullet: str) -> bool:
    match = re.match(r"[^A-Za-z]*([A-Za-z][A-Za-z\-]*)", bullet)
    return bool(match) and match.group(1).lower() in ACTION_VERBS


def _check(name: str, passed: bool, tip: str) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "tip": "" if passed else tip}


def run_ats_checks(parsed: dict[str, Any], sections: dict[str, list[str]], text: str,
                   page_count: int, links: list[str]) -> list[dict[str, Any]]:
    """Run the 10 ATS checks in a fixed order. Checks on bullets fail when there are no bullets."""
    bullets = [b for entry in parsed["projects"] + parsed["experience"] for b in entry["bullets"]]
    total = len(bullets)
    searchable = text + "\n" + "\n".join(links)

    has_email, has_phone = find_email(text), find_phone(text)
    missing_contact = [label for label, ok in (("email", has_email), ("phone number", has_phone)) if not ok]

    found_headings = [h for h in CORE_HEADINGS if sections.get(h)]
    is_fresher = len(parsed["experience"]) == 0

    verb_count = sum(_starts_with_action_verb(b) for b in bullets)
    number_count = sum(bool(re.search(r"\d", b)) for b in bullets)
    long_count = sum(len(b.split()) > MAX_BULLET_WORDS for b in bullets)

    return [
        _check("Contact details present", not missing_contact,
               "Add your " + " and ".join(missing_contact) + " at the top of the resume"),
        _check("Standard section headings", len(found_headings) >= MIN_STANDARD_HEADINGS,
               "Use standard headings such as Education, Skills, Projects, Experience"),
        _check("Education section present", bool(parsed["education"]),
               "Add an Education section with degree, college and year"),
        _check("Skills section present", bool(parsed["skills"]),
               "Add a Skills section listing your technical skills"),
        _check("One page for freshers", (not is_fresher) or page_count <= 1,
               "Freshers should keep the resume to one page"),
        _check("Bullet points used", total >= MIN_BULLETS,
               f"Describe your projects and experience in at least {MIN_BULLETS} bullet points"),
        _check("Bullets start with action verbs", total > 0 and verb_count / total >= ACTION_VERB_RATIO,
               "Start bullets with action verbs such as Built, Designed, Implemented"),
        _check("Bullets contain numbers", total > 0 and number_count / total >= NUMBER_RATIO,
               "Add measurable results (percentages, counts, time saved)"),
        _check("No overly long bullets", total > 0 and long_count == 0,
               f"Keep each bullet under {MAX_BULLET_WORDS} words"),
        _check("GitHub or LinkedIn link", bool(_LINK_RE.search(searchable)),
               "Add your GitHub or LinkedIn profile link"),
    ]


def compute_ats_score(checks: list[dict[str, Any]]) -> int:
    """Equal-weight score: share of passed checks, 0-100 (implementation decision)."""
    if not checks:
        return 0
    return int(100 * sum(c["passed"] for c in checks) / len(checks) + 0.5)


# --------------------------------------------------------------------------
# D. Keyword matching
# --------------------------------------------------------------------------
def technical_vocabulary() -> frozenset[str]:
    """All keywords of all roles: the only terms a job description may contribute."""
    return frozenset(kw for words in load_role_keywords().values() for kw in words)


def extract_jd_keywords(jd_text: str, base_keywords: list[str],
                        min_count: int = JD_MIN_COUNT, max_keywords: int = JD_MAX_KEYWORDS) -> list[str]:
    """Frequent technical terms of the JD that are not already in the role list."""
    jd_norm = normalize_text(jd_text)
    if not jd_norm:
        return []
    base = set(base_keywords)
    counted = [(count_term(jd_norm, term), term) for term in technical_vocabulary() if term not in base]
    qualified = sorted((-n, term) for n, term in counted if n >= min_count)
    return [term for _, term in qualified[:max_keywords]]


def match_keywords(text: str, keywords: list[str]) -> dict[str, list[str]]:
    """Split ``keywords`` into matched / missing against the resume text (order preserved)."""
    norm = normalize_text(text)
    matched, missing = [], []
    for kw in keywords:
        (matched if count_term(norm, kw) > 0 else missing).append(kw)
    return {"matched": matched, "missing": missing}


# --------------------------------------------------------------------------
# E. LLM feedback (one call) + validation + fallback
# --------------------------------------------------------------------------
LLM_SYSTEM = "You are a strict ATS resume reviewer for students. Reply with JSON only."


def _default_llm() -> Optional[Callable[..., Any]]:
    try:
        from llm import ask_llm  # shared Ollama gateway owned by Member 5
        return ask_llm
    except Exception as exc:
        logger.warning("llm.ask_llm not importable: %s", exc)
        return None


def collect_bullets(parsed: dict[str, Any]) -> list[str]:
    return [b for entry in parsed["projects"] + parsed["experience"] for b in entry["bullets"]]


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def build_feedback_prompt(role: str, parsed: dict[str, Any], keywords: dict[str, list[str]],
                          checks: list[dict[str, Any]], bullets: list[str]) -> str:
    failed = [c["name"] for c in checks if not c["passed"]]
    numbered = "\n".join(f"{i + 1}. {_truncate(b, MAX_PROMPT_BULLET_CHARS)}" for i, b in enumerate(bullets))
    return (
        f"Target role: {role or 'not specified'}\n"
        f"Skills listed: {', '.join(parsed['skills'][:25]) or 'none'}\n"
        f"Education: {'; '.join(parsed['education'][:3]) or 'none'}\n"
        f"Keywords found: {', '.join(keywords['matched']) or 'none'}\n"
        f"Keywords missing: {', '.join(keywords['missing'][:15]) or 'none'}\n"
        f"Failed ATS checks: {', '.join(failed) or 'none'}\n"
        f"Resume bullets:\n{numbered or '(no bullets found)'}\n\n"
        "Give feedback as JSON with exactly these keys:\n"
        '{"strengths": ["..."], "weaknesses": ["..."], '
        '"rewrites": [{"original": "...", "improved": "..."}]}\n'
        "Rules: 3 strengths, 3 weaknesses, exactly "
        f"{min(REWRITE_COUNT, len(bullets))} rewrites. Each rewrite's \"original\" must be copied word for word "
        "from the numbered bullets above. In \"improved\", start with a strong action verb and add a measurable "
        "result. Do not invent numbers or tools: if a number is unknown write a placeholder such as [X%]. "
        "Do not include any links."
    )


def _clean_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    items = [_truncate(v.strip(), MAX_FEEDBACK_CHARS) for v in value if isinstance(v, str) and v.strip()]
    return items[:MAX_FEEDBACK_ITEMS]


def _bullet_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def validate_feedback(raw: Any, source_bullets: list[str]) -> Optional[dict[str, Any]]:
    """Return a clean feedback dict, or None if the LLM output is unusable.

    Accepted only if: JSON object without "error"; >=1 strength; >=1 weakness; and the required number
    (3, or fewer if the resume has fewer bullets) of rewrites whose "original" really is a resume bullet.
    Unknown extra fields are dropped. The "original" is replaced by the exact resume bullet text.
    """
    if not isinstance(raw, dict) or "error" in raw:
        return None
    strengths, weaknesses = _clean_str_list(raw.get("strengths")), _clean_str_list(raw.get("weaknesses"))
    if not strengths or not weaknesses:
        return None
    required = min(REWRITE_COUNT, len(source_bullets))
    keyed = [(_bullet_key(b), b) for b in source_bullets]
    rewrites: list[dict[str, str]] = []
    used: set[str] = set()
    raw_rewrites = raw.get("rewrites") if isinstance(raw.get("rewrites"), list) else []
    for item in raw_rewrites:
        if not isinstance(item, dict) or not isinstance(item.get("original"), str) \
                or not isinstance(item.get("improved"), str):
            continue
        key, improved = _bullet_key(item["original"]), item["improved"].strip()
        if len(key) < 8 or not improved:
            continue
        for bullet_key, bullet in keyed:
            if bullet not in used and (key in bullet_key or bullet_key in key):
                used.add(bullet)
                rewrites.append({"original": bullet, "improved": _truncate(improved, 400)})
                break
    if len(rewrites) < required:
        return None
    return {"strengths": strengths, "weaknesses": weaknesses, "rewrites": rewrites[:required]}


def fallback_feedback(checks: list[dict[str, Any]], text_readable: bool) -> dict[str, Any]:
    """Deterministic feedback used when the LLM is unavailable or returns unusable output."""
    if not text_readable:
        return {"strengths": [],
                "weaknesses": ["No readable text was found in this PDF. Upload a text-based PDF, not a scan or photo."],
                "rewrites": []}
    strengths = [f"{c['name']}" for c in checks if c["passed"]][:3]
    weaknesses = [c["tip"] for c in checks if not c["passed"]][:3]
    return {"strengths": strengths or ["Resume text was read successfully."],
            "weaknesses": weaknesses or ["Tailor your keywords to the target role and job description."],
            "rewrites": []}


def get_llm_feedback(role: str, parsed: dict[str, Any], keywords: dict[str, list[str]],
                     checks: list[dict[str, Any]], llm: Optional[Callable[..., Any]] = None) -> dict[str, Any]:
    """One JSON-mode LLM call; validated; falls back safely. Never raises."""
    bullets = collect_bullets(parsed)[:MAX_PROMPT_BULLETS]
    llm = llm or _default_llm()
    if llm is None:
        return fallback_feedback(checks, True)
    try:
        raw = llm(build_feedback_prompt(role, parsed, keywords, checks, bullets),
                  system=LLM_SYSTEM, want_json=True, temperature=0.3)
    except Exception as exc:
        logger.warning("LLM call failed: %s", exc)
        return fallback_feedback(checks, True)
    feedback = validate_feedback(raw, bullets)
    if feedback is None:
        logger.warning("LLM feedback rejected (error, wrong shape or bad rewrites)")
        return fallback_feedback(checks, True)
    return feedback


# --------------------------------------------------------------------------
# F. Public entry point
# --------------------------------------------------------------------------
def _empty_result(message: str) -> dict[str, Any]:
    return {"parsed": {"name": "", "skills": [], "projects": [], "experience": [], "education": []},
            "ats_score": 0, "ats_checks": [], "keywords": {"matched": [], "missing": []},
            "feedback": {"strengths": [], "weaknesses": [message], "rewrites": []}}


def analyze_resume(pdf_bytes: bytes, role: str, jd_text: str = "",
                   llm: Optional[Callable[..., Any]] = None) -> dict[str, Any]:
    """Analyse a resume PDF. See module docstring for the returned shape. Never raises.

    ``llm`` is an optional replacement for llm.ask_llm (used by tests); leave None in production.
    """
    try:
        extracted = extract_pdf(pdf_bytes)
        text = extracted["text"]
        readable = len(text.split()) >= MIN_TEXT_WORDS
        if extracted["error"]:
            logger.warning("Extraction problem: %s", extracted["error"])

        sections = split_sections(text)
        parsed = parse_resume(sections)
        checks = run_ats_checks(parsed, sections, text, extracted["pages"], extracted["links"])

        role_key = resolve_role(role)
        if role_key is None:
            logger.warning("Unknown role %r: only job-description keywords will be used", role)
        base_keywords = load_role_keywords().get(role_key, []) if role_key else []
        jd_keywords = extract_jd_keywords(jd_text, base_keywords) if isinstance(jd_text, str) else []
        keywords = match_keywords(text, base_keywords + jd_keywords)

        if readable:
            feedback = get_llm_feedback(role_key or str(role or ""), parsed, keywords, checks, llm)
        else:
            feedback = fallback_feedback(checks, False)

        return {"parsed": parsed, "ats_score": compute_ats_score(checks), "ats_checks": checks,
                "keywords": keywords, "feedback": feedback}
    except Exception:
        logger.exception("analyze_resume failed unexpectedly")
        return _empty_result("The resume could not be analysed. Please try another PDF.")


# --------------------------------------------------------------------------
# Command line: python resume.py sample.pdf [role] [jd.txt]
# --------------------------------------------------------------------------
def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Usage: python resume.py sample.pdf [role] [jd.txt]", file=sys.stderr)
        return 2
    try:
        pdf_bytes = Path(argv[1]).read_bytes()
        jd_text = Path(argv[3]).read_text(encoding="utf-8") if len(argv) > 3 else ""
    except OSError as exc:
        print(f"Cannot read input file: {exc}", file=sys.stderr)
        return 1
    role = argv[2] if len(argv) > 2 else "SDE"
    print(json.dumps(analyze_resume(pdf_bytes, role, jd_text), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
