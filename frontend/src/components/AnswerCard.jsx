/* One answer in the final report: question, what the student said, and feedback. */
import { useState } from "react";
import { QUESTION_TYPES } from "./questionTypes";

export default function AnswerCard({ answer, number }) {
  const [open, setOpen] = useState(number === 1);
  const ev = answer.evaluation || {};
  const score = typeof ev.score === "number" ? ev.score : null;

  return (
    <article className={`answer-card ${open ? "open" : ""}`}>
      <button className="answer-head" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className="answer-num">{number}</span>
        <span className="answer-q">
          <span className="answer-type">{QUESTION_TYPES[answer.type] || "Question"}</span>
          {answer.question}
        </span>
        <span className={`answer-score ${score === null ? "none" : score >= 7 ? "good" : score >= 5 ? "ok" : "low"}`}>
          {score === null ? "—" : `${score}/10`}
        </span>
      </button>

      {open && (
        <div className="answer-body">
          <h4>Your answer {answer.input_mode === "voice" ? "(spoken)" : "(typed)"}</h4>
          <p className="transcript">{answer.transcript}</p>

          {(answer.speech || answer.gaze) && (
            <div className="stat-row">
              {answer.speech && (
                <>
                  <span><b>{answer.speech.wpm ?? "—"}</b> words/min</span>
                  <span><b>{answer.speech.filler_count ?? 0}</b> filler words</span>
                  <span><b>{answer.speech.long_pauses ?? 0}</b> long pauses</span>
                </>
              )}
              {answer.gaze && answer.gaze.tracking_quality === "good" && (
                <>
                  <span><b>{answer.gaze.eye_contact_pct}%</b> eye contact</span>
                  <span><b>{answer.gaze.look_away_count}</b> look-aways</span>
                </>
              )}
            </div>
          )}

          <div className="two-col">
            <div>
              <h4>What worked</h4>
              <ul>{(ev.strengths || []).map((s, i) => <li key={i}>{s}</li>)}</ul>
              {!(ev.strengths || []).length && <p className="muted">No strengths noted.</p>}
            </div>
            <div>
              <h4>What was missing</h4>
              <ul>{(ev.missing_points || []).map((s, i) => <li key={i}>{s}</li>)}</ul>
              {!(ev.missing_points || []).length && <p className="muted">Nothing major missing.</p>}
            </div>
          </div>

          {ev.better_answer && (
            <div className="better">
              <h4>A stronger answer</h4>
              <p>{ev.better_answer}</p>
            </div>
          )}
          {ev.note && <p className="muted">{ev.note}</p>}
        </div>
      )}
    </article>
  );
}
