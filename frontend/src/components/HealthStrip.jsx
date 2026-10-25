/* Shows whether the local AI parts are running (proves the app is offline/on-device). */
import { useEffect, useState } from "react";
import { getHealth } from "../api";

export default function HealthStrip() {
  const [health, setHealth] = useState(null);
  const [down, setDown] = useState(false);

  useEffect(() => {
    getHealth().then(setHealth).catch(() => setDown(true));
  }, []);

  if (down) {
    return <p className="health health-down">Backend is not running. In the backend folder run: uvicorn main:app --port 8000</p>;
  }
  if (!health) return <p className="health">Checking local AI…</p>;

  const items = [
    ["Local language model", health.ollama],
    ["Speech recognition", health.whisper],
    ["Integrity check", health.shield === "available"],
  ];
  return (
    <ul className="health" aria-label="Local AI status">
      {items.map(([name, ok]) => (
        <li key={name} className={ok ? "ok" : "bad"}>
          <span className="health-dot" aria-hidden="true" />
          {name}
          {!ok && name === "Local language model" && " — start Ollama"}
        </li>
      ))}
    </ul>
  );
}
