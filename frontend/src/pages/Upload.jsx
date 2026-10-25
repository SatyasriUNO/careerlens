import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { analyzeResume } from "../api";
import { useApp } from "../store";
import HealthStrip from "../components/HealthStrip";
import Spinner from "../components/Spinner";

export const ROLES = ["SDE", "Data Analyst", "ML Engineer", "Embedded", "Web Developer"];

export default function Upload() {
  const { state, update } = useApp();
  const navigate = useNavigate();
  const inputRef = useRef(null);

  const [file, setFile] = useState(null);
  const [role, setRole] = useState(state.role || ROLES[0]);
  const [jdText, setJdText] = useState(state.jdText || "");
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const pickFile = (f) => {
    setError("");
    if (!f) return;
    if (!f.name.toLowerCase().endsWith(".pdf")) {
      setError("Please choose a PDF file.");
      return;
    }
    if (f.size > 5 * 1024 * 1024) {
      setError("This PDF is larger than 5 MB. Export a smaller version of your resume.");
      return;
    }
    setFile(f);
  };

  const submit = async () => {
    if (!file) {
      setError("Choose your resume PDF first.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const result = await analyzeResume(file, role, jdText);
      update({ role, jdText, resume: result, sessionId: null, report: null });
      navigate("/resume");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="upload">
      <div className="hero">
        <h1>Practise for placements with an interviewer that has read your resume.</h1>
        <p className="lead">
          Upload your resume, get an ATS check, then answer five interview questions about your own projects.
          Everything runs on this laptop — nothing is uploaded to the internet.
        </p>
        <HealthStrip />
      </div>

      <div className="panel form-panel">
        <label className="field">
          <span>Target role</span>
          <select value={role} onChange={(e) => setRole(e.target.value)} disabled={busy}>
            {ROLES.map((r) => (
              <option key={r}>{r}</option>
            ))}
          </select>
        </label>

        <div
          className={`dropzone ${dragging ? "drag" : ""} ${file ? "has-file" : ""}`}
          onClick={() => !busy && inputRef.current && inputRef.current.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            pickFile(e.dataTransfer.files[0]);
          }}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && inputRef.current && inputRef.current.click()}
        >
          <input
            ref={inputRef}
            type="file"
            accept="application/pdf,.pdf"
            hidden
            onChange={(e) => pickFile(e.target.files[0])}
          />
          {file ? (
            <>
              <strong>{file.name}</strong>
              <span className="muted">Click to choose a different file</span>
            </>
          ) : (
            <>
              <strong>Drop your resume PDF here</strong>
              <span className="muted">or click to choose a file (max 5 MB)</span>
            </>
          )}
        </div>

        <label className="field">
          <span>Job description <em className="muted">(optional)</em></span>
          <textarea
            rows={5}
            placeholder="Paste the job description to check your resume against it"
            value={jdText}
            onChange={(e) => setJdText(e.target.value)}
            disabled={busy}
          />
        </label>

        {error && <p className="error">{error}</p>}
        {busy ? (
          <Spinner label="Reading your resume… this takes about 20 seconds" />
        ) : (
          <button className="btn btn-primary" onClick={submit}>
            Analyse my resume
          </button>
        )}
      </div>
    </section>
  );
}
