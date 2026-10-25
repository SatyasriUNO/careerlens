import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { finishInterview, startInterview, submitAnswer } from "../api";
import { useApp } from "../store";
import useRecorder from "../hooks/useRecorder";
import useGaze from "../gaze/useGaze";
import GazeWidget from "../gaze/GazeWidget";
import ShieldLight from "../components/ShieldLight";
import Spinner from "../components/Spinner";
import { QUESTION_TYPES } from "../components/questionTypes";
import { deviceLabel } from "../devices";

const clock = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

export default function InterviewRoom() {
  const { state, update } = useApp();
  const navigate = useNavigate();
  const gaze = useGaze();
  const rec = useRecorder();

  // setup | starting | question | submitting | feedback | finishing
  const [phase, setPhase] = useState("setup");
  const [consent, setConsent] = useState(true);
  const [sessionId, setSessionId] = useState(null);
  const [question, setQuestion] = useState(null);
  const [mode, setMode] = useState("voice");
  const [typed, setTyped] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  if (!state.resume) {
    return (
      <div className="empty">
        <p>Upload your resume first so the interviewer can ask about it.</p>
        <Link className="btn btn-primary" to="/">Upload a resume</Link>
      </div>
    );
  }

  const showQuestion = (q) => {
    setQuestion(q);
    setTyped("");
    rec.reset();
    setResult(null);
    setError("");
    setPhase("question");
    gaze.startAnswer();
  };

  const begin = async () => {
    setError("");
    setPhase("starting");
    try {
      const res = await startInterview(state.resume.resume_id, state.role, consent);
      setSessionId(res.session_id);
      update({ sessionId: res.session_id, report: null });
      showQuestion(res.question);
    } catch (e) {
      setError(e.message);
      setPhase("setup");
    }
  };

  const submit = async () => {
    setError("");
    if (mode === "voice") {
      if (rec.recording) {
        setError("Stop the recording first, then submit.");
        return;
      }
      if (!rec.blob) {
        setError("Record your answer first, or switch to typing.");
        return;
      }
    } else if (typed.trim().length < 3) {
      setError("Type your answer first.");
      return;
    }

    const gazeData = gaze.stopAnswer();
    setPhase("submitting");
    try {
      const res = await submitAnswer({
        sessionId,
        questionId: question.id,
        audioBlob: mode === "voice" ? rec.blob : null,
        typedText: mode === "type" ? typed.trim() : "",
        gaze: gazeData,
      });
      setResult(res);
      setPhase("feedback");
    } catch (e) {
      setError(e.message);
      setPhase("question");
      gaze.startAnswer();
    }
  };

  const finish = async () => {
    setError("");
    setPhase("finishing");
    try {
      const report = await finishInterview(sessionId);
      update({ report, sessionId: null });
      gaze.stop();
      navigate("/report");
    } catch (e) {
      setError(e.message);
      setPhase(result ? "feedback" : "question");
    }
  };

  const next = () => {
    if (result && result.next_question) showQuestion(result.next_question);
    else finish();
  };

  const ev = (result && result.evaluation) || {};

  return (
    <section className="interview">
      <div className="interview-main">
        {phase === "setup" || phase === "starting" ? (
          <div className="panel">
            <h1>Before you start</h1>
            <p className="lead">
              You will get five questions for the <b>{state.role}</b> role. Two of them are about claims on your own resume.
              Answer by speaking (best) or by typing.
            </p>
            <ol className="steps">
              <li>Turn on the camera on the right for eye-contact feedback. This is optional — the video never leaves this laptop.</li>
              <li>Press <b>Check my eye line</b> and look at the camera for 3 seconds.</li>
              <li>Answer each question, then read the feedback before moving on.</li>
            </ol>
            <label className="consent">
              <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
              <span>
                Run the integrity check during this interview. It looks for hidden AI-assistant windows and known copilot apps
                on this laptop. It does not read your files, screen or browsing.
              </span>
            </label>
            {error && <p className="error">{error}</p>}
            {phase === "starting" ? (
              <Spinner label="Preparing questions from your resume… (up to 30 seconds)" />
            ) : (
              <button className="btn btn-primary" onClick={begin}>Start interview</button>
            )}
          </div>
        ) : null}

        {question && phase !== "setup" && phase !== "starting" && (
          <div className="panel question-card">
            <div className="q-meta">
              <span>Question {question.index} of {question.total}</span>
              <span className="chip chip-type">{QUESTION_TYPES[question.type] || "Question"}</span>
            </div>
            <p className="q-text">{question.text}</p>
          </div>
        )}

        {phase === "question" && (
          <div className="panel">
            <div className="mode-tabs" role="tablist">
              <button role="tab" aria-selected={mode === "voice"} className={mode === "voice" ? "active" : ""} onClick={() => setMode("voice")}>
                Speak
              </button>
              <button role="tab" aria-selected={mode === "type"} className={mode === "type" ? "active" : ""} onClick={() => { rec.reset(); setMode("type"); }}>
                Type
              </button>
            </div>

            {mode === "voice" ? (
              <div className="recorder">
                {!rec.recording && !rec.blob && (
                  <button className="btn btn-record" onClick={rec.start}>
                    <span className="rec-dot" aria-hidden="true" /> Start recording
                  </button>
                )}
                {rec.recording && (
                  <>
                    <button className="btn btn-record recording" onClick={rec.stop}>
                      <span className="rec-dot" aria-hidden="true" /> Stop · {clock(rec.seconds)}
                    </button>
                    <div className="meter" aria-label="Microphone level">
                      <div className="meter-fill" style={{ width: `${Math.round(rec.level * 100)}%` }} />
                    </div>
                    <p className="muted small">The bar should move when you speak. If it stays still, stop and pick another microphone.</p>
                  </>
                )}
                {!rec.recording && rec.blob && (
                  <div className="rec-done">
                    <span>Recording saved ({clock(rec.seconds)})</span>
                    <button className="btn btn-ghost" onClick={() => { rec.reset(); gaze.startAnswer(); }}>Record again</button>
                  </div>
                )}

                {rec.mics.length > 0 && !rec.recording && (
                  <label className="mic-pick">
                    <span>Microphone</span>
                    <select value={rec.micId || ""} onChange={(e) => { rec.reset(); rec.selectMic(e.target.value); }}>
                      {!rec.micId && <option value="">Default microphone</option>}
                      {rec.mics.map((m, i) => (
                        <option key={m.deviceId} value={m.deviceId}>{deviceLabel(m, i, "audioinput")}</option>
                      ))}
                    </select>
                  </label>
                )}

                <p className="muted small">Aim for 45–90 seconds. Speak at a normal pace.</p>
                {rec.warning && <p className="warn">{rec.warning}</p>}
                {rec.error && <p className="error">{rec.error}</p>}
              </div>
            ) : (
              <textarea
                className="answer-box"
                rows={7}
                placeholder="Type your answer here"
                value={typed}
                onChange={(e) => setTyped(e.target.value)}
              />
            )}

            {error && (
              <div className="error-box">
                <p className="error">{error}</p>
                {mode === "voice" && (
                  <button className="btn btn-ghost" onClick={() => { rec.reset(); setError(""); setMode("type"); }}>
                    Type this answer instead
                  </button>
                )}
              </div>
            )}
            <div className="row-end">
              {question.index > 1 && (
                <button className="btn btn-ghost" onClick={finish}>Finish now</button>
              )}
              <button className="btn btn-primary" onClick={submit} disabled={rec.recording}>Submit answer</button>
            </div>
          </div>
        )}

        {phase === "submitting" && (
          <div className="panel">
            <Spinner label="Transcribing and scoring your answer… (10–30 seconds)" />
          </div>
        )}

        {phase === "feedback" && result && (
          <div className="panel feedback">
            <div className="feedback-head">
              <h3>Feedback</h3>
              <span className={`score-pill ${typeof ev.score !== "number" ? "none" : ev.score >= 7 ? "good" : ev.score >= 5 ? "ok" : "low"}`}>
                {typeof ev.score === "number" ? `${ev.score}/10` : "Not scored"}
              </span>
            </div>
            <h4>{result.input_mode === "voice" ? "We heard" : "Your answer"}</h4>
            <p className="transcript">{result.transcript}</p>
            {result.speech && (
              <div className="stat-row">
                <span><b>{result.speech.wpm ?? "—"}</b> words/min</span>
                <span><b>{result.speech.filler_count ?? 0}</b> filler words</span>
                <span><b>{result.speech.long_pauses ?? 0}</b> long pauses</span>
                {result.gaze && result.gaze.tracking_quality === "good" && (
                  <span><b>{result.gaze.eye_contact_pct}%</b> eye contact</span>
                )}
              </div>
            )}
            <div className="two-col">
              <div>
                <h4>What worked</h4>
                <ul>{(ev.strengths || []).map((s, i) => <li key={i}>{s}</li>)}</ul>
              </div>
              <div>
                <h4>What was missing</h4>
                <ul>{(ev.missing_points || []).map((s, i) => <li key={i}>{s}</li>)}</ul>
              </div>
            </div>
            {ev.better_answer && (
              <div className="better">
                <h4>A stronger answer</h4>
                <p>{ev.better_answer}</p>
              </div>
            )}
            {ev.note && <p className="muted">{ev.note}</p>}
            {error && <p className="error">{error}</p>}
            <div className="row-end">
              <button className="btn btn-primary" onClick={next}>
                {result.next_question ? "Next question" : "Finish and see my report"}
              </button>
            </div>
          </div>
        )}

        {phase === "finishing" && (
          <div className="panel">
            <Spinner label="Building your report and learning plan…" />
          </div>
        )}
      </div>

      <aside className="interview-side">
        <GazeWidget gaze={gaze} />
        {phase !== "setup" && <ShieldLight polling={phase !== "finishing"} />}
        <div className="tip-box">
          <h4>Tips</h4>
          <ul>
            <li>Use situation → action → result for story questions.</li>
            <li>Mention one number that shows your impact.</li>
            <li>Glancing away to think is normal.</li>
          </ul>
        </div>
      </aside>
    </section>
  );
}
