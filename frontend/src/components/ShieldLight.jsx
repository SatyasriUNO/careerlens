/*
 * ShieldLight.jsx — CopilotShield status light.
 * Polls GET /api/shield/status every 2 seconds while `polling` is true.
 */
import { useEffect, useState } from "react";
import { getShieldStatus } from "../api";

export default function ShieldLight({ polling = true }) {
  const [data, setData] = useState(null);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    if (!polling) return undefined;
    let alive = true;
    const check = async () => {
      try {
        const res = await getShieldStatus();
        if (alive) {
          setData(res);
          setOffline(false);
        }
      } catch {
        if (alive) setOffline(true);
      }
    };
    check();
    const id = setInterval(check, 2000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [polling]);

  let tone = "grey";
  let text = "Integrity check: starting…";
  let title = "";
  if (offline) {
    text = "Integrity check: backend not reachable";
  } else if (data) {
    title = data.reason || "";
    if (data.status === "alert") {
      tone = "red";
      const f = data.findings && data.findings[0];
      text = `Hidden assistant detected${f ? `: ${f.name}` : ""}`;
    } else if (data.status === "unavailable") {
      text = "Integrity check: unavailable";
    } else if (!data.active) {
      text = "Integrity check: not running";
    } else {
      tone = "green";
      text = "No AI assistants detected";
    }
  }

  return (
    <div className={`shield shield-${tone}`} title={title} role="status" aria-live="polite">
      <span className="shield-dot" aria-hidden="true" />
      <span>{text}</span>
    </div>
  );
}
