/* Horizontal score bar with a note ("text-based", "not measured"...). */
export default function ScoreBar({ label, value, note }) {
  const measured = typeof value === "number";
  const pct = measured ? Math.max(0, Math.min(100, value)) : 0;
  const tone = !measured ? "none" : pct >= 70 ? "good" : pct >= 50 ? "ok" : "low";
  return (
    <div className="scorebar">
      <div className="scorebar-head">
        <span className="scorebar-label">{label}</span>
        <span className="scorebar-value">{measured ? Math.round(pct) : "Not measured"}</span>
      </div>
      <div className="scorebar-track">
        <div className={`scorebar-fill tone-${tone}`} style={{ width: `${pct}%` }} />
      </div>
      {measured && note && note !== "measured" && <p className="scorebar-note">Based on: {note}</p>}
    </div>
  );
}
