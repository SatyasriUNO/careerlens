/*
 * GazeDebug.jsx  —  Member 4 testing page (not shown to users)
 *
 * Shows the raw numbers so you can tune GAZE_SETTINGS in useGaze.js.
 * Member 1 adds one route in App.jsx:   <Route path="/gaze-debug" element={<GazeDebug />} />
 * Then open http://localhost:5173/gaze-debug
 *
 * Test routine:
 *   1. Turn on camera, then "Check my eye line".
 *   2. Press "Start answer", look at the camera 5 s, look away 2 s, look back. Repeat 3 times.
 *   3. Press "Stop answer". Expect look_away_count = 3 and eye_contact_pct around 60-75.
 */

import { useEffect, useState } from "react";
import useGaze, { GAZE_SETTINGS } from "./useGaze";
import GazeWidget from "./GazeWidget";

const fmt = (n) => (typeof n === "number" ? n.toFixed(3) : "—");

export default function GazeDebug() {
  const gaze = useGaze();
  const [debug, setDebug] = useState({});
  const [result, setResult] = useState(null);
  const [answering, setAnswering] = useState(false);

  useEffect(() => {
    const id = setInterval(() => setDebug({ ...gaze.debugRef.current }), 200);
    return () => clearInterval(id);
  }, [gaze.debugRef]);

  const base = debug.baseline;
  const rows = [
    ["Iris sideways (h)", debug.h, base && base.h, GAZE_SETTINGS.irisH],
    ["Iris up/down (v)", debug.v, base && base.v, GAZE_SETTINGS.irisV],
    ["Head turn (yaw)", debug.yaw, base && base.yaw, GAZE_SETTINGS.yaw],
    ["Head tilt (pitch)", debug.pitch, base && base.pitch, GAZE_SETTINGS.pitch],
    ["Eye openness", debug.open, null, GAZE_SETTINGS.blinkOpenness],
  ];

  return (
    <div style={{ padding: 24, fontFamily: "system-ui, sans-serif", display: "flex", gap: 32, flexWrap: "wrap" }}>
      <GazeWidget gaze={gaze} />

      <div style={{ minWidth: 380 }}>
        <h2 style={{ marginTop: 0 }}>GazeGuard debug</h2>
        <p>Status: <b>{gaze.status}</b> · Looking: <b>{String(Boolean(debug.looking))}</b> · Face: <b>{String(debug.face !== false)}</b></p>

        <table style={{ borderCollapse: "collapse", fontSize: 14 }}>
          <thead>
            <tr>
              {["Measure", "Now", "Baseline", "Allowed ±", "Difference"].map((h) => (
                <th key={h} style={{ textAlign: "left", padding: "4px 12px 4px 0" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(([name, now, b, tol]) => {
              const diff = typeof now === "number" && typeof b === "number" ? Math.abs(now - b) : null;
              const over = diff !== null && diff > tol;
              return (
                <tr key={name}>
                  <td style={{ padding: "4px 12px 4px 0" }}>{name}</td>
                  <td>{fmt(now)}</td>
                  <td>{fmt(b)}</td>
                  <td>{fmt(tol)}</td>
                  <td style={{ color: over ? "#E0245E" : "#0E9F6E", fontWeight: 600 }}>{fmt(diff)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>

        <div style={{ marginTop: 16, display: "flex", gap: 8 }}>
          <button
            disabled={answering || gaze.status !== "ready"}
            onClick={() => {
              setResult(null);
              gaze.startAnswer();
              setAnswering(true);
            }}
          >
            Start answer
          </button>
          <button
            disabled={!answering}
            onClick={() => {
              setResult(gaze.stopAnswer());
              setAnswering(false);
            }}
          >
            Stop answer
          </button>
        </div>

        <pre style={{ marginTop: 16, background: "#EFEBFB", padding: 12, borderRadius: 8 }}>
          {result ? JSON.stringify(result, null, 2) : "Answer result appears here"}
        </pre>
      </div>
    </div>
  );
}
