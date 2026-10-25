import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getReport } from "../api";
import { useApp } from "../store";
import ScoreBar from "../components/ScoreBar";
import AnswerCard from "../components/AnswerCard";
import Spinner from "../components/Spinner";

const SCORE_LABELS = [
  ["communication", "Communication"],
  ["confidence", "Confidence"],
  ["technical", "Technical knowledge"],
  ["resume", "Resume strength"],
];

function IntegrityBlock({ integrity }) {
  if (!integrity) return null;
  const { status, events = [], reason } = integrity;
  const text =
    status === "clear"
      ? "No hidden AI assistants or known copilot apps were found during this interview."
      : status === "alert"
      ? "Possible AI assistance was found. These are signals for review, not a verdict."
      : reason || "The integrity check did not run for this interview.";
  return (
    <div className={`panel integrity integrity-${status}`}>
      <h3>Integrity check: {status === "clear" ? "Clear" : status === "alert" ? "Needs review" : "Not checked"}</h3>
      <p>{text}</p>
      {events.length > 0 && (
        <ul className="events">
          {events.map((e, i) => (
            <li key={i}>
              <b>{e.time}</b> · {e.type === "hidden_overlay" ? "Hidden window" : "Known copilot app"}: {e.name}
              {e.detail ? ` — ${e.detail}` : ""}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function FinalReport() {
  const { sessionId } = useParams();
  const { state } = useApp();
  const [report, setReport] = useState(sessionId ? null : state.report);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!sessionId) {
      setReport(state.report);
      return;
    }
    getReport(sessionId).then(setReport).catch((e) => setError(e.message));
  }, [sessionId, state.report]);

  if (error) return <p className="error">{error}</p>;
  if (sessionId && !report) return <Spinner label="Loading report…" />;
  if (!report) {
    return (
      <div className="empty">
        <p>No report yet. Finish a mock interview to see one here.</p>
        <Link className="btn btn-primary" to="/">Start practising</Link>
      </div>
    );
  }

  const scores = report.scores || {};
  const notes = report.score_notes || {};

  return (
    <section>
      <div className="page-head">
        <div>
          <h1>Your interview report</h1>
          <p className="muted">Role: {report.role}</p>
        </div>
        <div className="row-end">
          <button className="btn btn-ghost" onClick={() => window.print()}>Print / save PDF</button>
          <Link className="btn btn-primary" to="/">Practise again</Link>
        </div>
      </div>

      <div className="panel scores">
        {SCORE_LABELS.map(([key, label]) => (
          <ScoreBar key={key} label={label} value={scores[key]} note={notes[key]} />
        ))}
      </div>

      <IntegrityBlock integrity={report.integrity} />

      <h2 className="section-title">Answer by answer</h2>
      {(report.answers || []).map((a, i) => (
        <AnswerCard key={i} answer={a} number={i + 1} />
      ))}

      <h2 className="section-title">Your 2-week learning plan</h2>
      {(report.roadmap || []).length === 0 ? (
        <p className="muted">No gaps found that need a plan. Keep practising.</p>
      ) : (
        <div className="panel">
          <table className="roadmap">
            <thead>
              <tr>
                <th>Days</th>
                <th>Skill</th>
                <th>Why</th>
                <th>Free resources</th>
              </tr>
            </thead>
            <tbody>
              {report.roadmap.map((item, i) => (
                <tr key={i}>
                  <td>{item.days || "—"}</td>
                  <td><b>{item.skill}</b></td>
                  <td>{item.why}</td>
                  <td>
                    {(item.resources || []).length
                      ? item.resources.map((res, j) => (
                          <a key={j} href={res.url} target="_blank" rel="noreferrer">{res.title}</a>
                        ))
                      : <span className="muted">—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
