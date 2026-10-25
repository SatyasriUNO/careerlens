# Integration check — what changed

Checked: resume.py, scoring.py, resources.json, role_keywords.json (Member 2) and interview.py, question_bank.json (Member 3), together with main.py (Member 5).

## No changes needed
- **resume.py** — parsed a test resume correctly (name, skills, projects, bullets, education), 10 ATS checks, keyword matching and LLM feedback validation all work. Never crashes on bad PDFs.
- **scoring.py** — Section 7 formulas are exact; "not measured" handled properly.
- **resources.json** — 51 skills, 121 https links; every keyword in role_keywords.json has a resource.
- **role_keywords.json** — role names match the frontend exactly.

## Fixed: interview.py (Member 3)
1. **Wrong technical questions for every role.** The question bank was keyed by frontend/backend/devops/data, but the app sends SDE / Data Analyst / ML Engineer / Embedded / Web Developer, so every student got a JavaScript or CSS question (an Embedded student was asked about `let` vs `var`). Now uses the 5 real roles.
2. **Both resume-claim questions were identical** whenever the LLM reworded a claim (it usually does) or was offline. Now the LLM picks bullets by number, duplicates are rejected, and the fallback uses two different bullets.
3. **Fake score when the LLM is down.** It returned 5/10 for every answer. Now it returns "Not scored" plus the key points the answer did not cover.
4. **LLM answers like "7/10"** made the whole evaluation fail. Now parsed correctly. Extra junk keys from the LLM are dropped.
5. **Transcripts had double spaces** between every word. Fixed.
6. **Whisper loads safely once**, on the CPU, even if two requests arrive together.
7. Fallback project questions never showed (wrong key name). Fixed.

## Fixed: question_bank.json (Member 3)
Re-keyed by the 5 roles, 5 technical questions each, all with key points. New questions written for **ML Engineer** and **Embedded** (there were none). Removed the CSS-specificity question because one of its key points was wrong (`!important` does override inline styles). Intro, behavioural and fallback questions kept.

## Fixed: main.py (Member 5)
1. **Technical score always showed "Not measured".** scoring.py reads the question type from `answer["question"]["type"]`; main.py sent it as `answer["type"]`. main.py now sends the shape scoring.py expects.
2. Weak answers for the roadmap now use Member 2's `select_weak_answers`.
3. Whisper now loads in the background when the backend starts, so the first spoken answer is not slow. `/api/health` reports `whisper_status`.

## Test result (fake LLM, sample resume, Embedded role)
Claim probes: two different questions quoting the student's own numbers · technical question: PWM · key points hidden from the browser · scores: communication 70 (text-based), confidence not measured (typed only), technical 60, resume 63 · roadmap: C, C++, Microcontrollers & Embedded C, RTOS.

Sample test resume: `backend/data/samples/sample_resume.pdf`
