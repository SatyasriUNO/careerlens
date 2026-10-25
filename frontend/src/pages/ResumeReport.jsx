import { Link, useNavigate } from "react-router-dom";
import { useApp } from "../store";
import ScoreRing from "../components/ScoreRing";
import KeywordChips from "../components/KeywordChips";

export default function ResumeReport() {
  const { state } = useApp();
  const navigate = useNavigate();
  const r = state.resume;

  if (!r) {
    return (
      <div className="empty">
        <p>No resume analysed yet.</p>
        <Link className="btn btn-primary" to="/">Upload a resume</Link>
      </div>
    );
  }

  const checks = r.ats_checks || [];
  const fb = r.feedback || {};
  const passed = checks.filter((c) => c.passed).length;

  return (
    <section>
      <div className="page-head">
        <div>
          <h1>Resume report</h1>
          <p className="muted">
            {r.parsed && r.parsed.name ? `${r.parsed.name} · ` : ""}Target role: {state.role}
          </p>
        </div>
        <button className="btn btn-primary" onClick={() => navigate("/interview")}>
          Start mock interview
        </button>
      </div>

      <div className="grid-resume">
        <div className="panel center">
          <ScoreRing value={r.ats_score} label="ATS score" size={160} />
          <p className="muted small">
            {passed} of {checks.length} checks passed
          </p>
        </div>

        <div className="panel">
          <h3>ATS checklist</h3>
          <ul className="checklist">
            {checks.map((c, i) => (
              <li key={i} className={c.passed ? "pass" : "fail"}>
                <span className="check-icon" aria-hidden="true">{c.passed ? "✓" : "!"}</span>
                <div>
                  <span>{c.name}</span>
                  {!c.passed && c.tip && <p className="tip">{c.tip}</p>}
                </div>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="panel">
        <h3>Keywords</h3>
        <KeywordChips matched={(r.keywords || {}).matched} missing={(r.keywords || {}).missing} />
      </div>

      <div className="two-col">
        <div className="panel">
          <h3>Strengths</h3>
          <ul>{(fb.strengths || []).map((s, i) => <li key={i}>{s}</li>)}</ul>
        </div>
        <div className="panel">
          <h3>To improve</h3>
          <ul>{(fb.weaknesses || []).map((s, i) => <li key={i}>{s}</li>)}</ul>
        </div>
      </div>

      {(fb.rewrites || []).length > 0 && (
        <div className="panel">
          <h3>Rewritten bullet points</h3>
          {fb.rewrites.map((rw, i) => (
            <div key={i} className="rewrite">
              <p className="before"><span>Before</span>{rw.original}</p>
              <p className="after"><span>After</span>{rw.improved}</p>
            </div>
          ))}
        </div>
      )}

      <div className="page-foot">
        <Link to="/" className="btn btn-ghost">Upload a different resume</Link>
        <button className="btn btn-primary" onClick={() => navigate("/interview")}>
          Start mock interview
        </button>
      </div>
    </section>
  );
}
