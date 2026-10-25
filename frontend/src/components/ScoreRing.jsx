/* Round gauge for a 0–100 score. Shows "Not measured" when value is null. */
export default function ScoreRing({ value, label, size = 132 }) {
  const r = 52;
  const circumference = 2 * Math.PI * r;
  const measured = typeof value === "number";
  const pct = measured ? Math.max(0, Math.min(100, value)) : 0;
  const color = !measured ? "var(--muted)" : pct >= 70 ? "var(--mint)" : pct >= 50 ? "var(--amber)" : "var(--pink)";

  return (
    <figure className="ring" style={{ width: size }}>
      <svg viewBox="0 0 120 120" width={size} height={size} aria-hidden="true">
        <circle cx="60" cy="60" r={r} fill="none" stroke="var(--lavender-2)" strokeWidth="10" />
        <circle
          cx="60"
          cy="60"
          r={r}
          fill="none"
          stroke={color}
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={`${(pct / 100) * circumference} ${circumference}`}
          transform="rotate(-90 60 60)"
        />
        <text x="60" y="58" textAnchor="middle" className="ring-value">
          {measured ? Math.round(pct) : "—"}
        </text>
        <text x="60" y="78" textAnchor="middle" className="ring-sub">
          {measured ? "out of 100" : "not measured"}
        </text>
      </svg>
      {label && <figcaption>{label}</figcaption>}
    </figure>
  );
}
