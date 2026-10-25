import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getHistory } from "../api";
import Spinner from "../components/Spinner";

const fmt = (v) => (typeof v === "number" ? Math.round(v) : "—");

export default function History() {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getHistory().then(setRows).catch((e) => setError(e.message));
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!rows) return <Spinner label="Loading your sessions…" />;

  return (
    <section>
      <div className="page-head">
        <h1>Practice history</h1>
        <Link className="btn btn-primary" to="/">New practice</Link>
      </div>
      {rows.length === 0 ? (
        <div className="empty">
          <p>No finished interviews yet. Complete one and it will appear here.</p>
        </div>
      ) : (
        <div className="panel">
          <table className="history">
            <thead>
              <tr>
                <th>Date</th>
                <th>Role</th>
                <th>Communication</th>
                <th>Confidence</th>
                <th>Technical</th>
                <th>Resume</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.session_id}>
                  <td>{r.date}</td>
                  <td>{r.role}</td>
                  <td>{fmt(r.scores?.communication)}</td>
                  <td>{fmt(r.scores?.confidence)}</td>
                  <td>{fmt(r.scores?.technical)}</td>
                  <td>{fmt(r.scores?.resume)}</td>
                  <td><Link to={`/report/${r.session_id}`}>Open report</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
