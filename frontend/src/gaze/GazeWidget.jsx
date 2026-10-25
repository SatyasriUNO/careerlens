/*
 * GazeWidget.jsx  —  Member 4 (GazeGuard-lite)
 *
 * Small webcam preview with live eye-contact feedback.
 * It does not create its own tracker: the page passes in the hook so the page can
 * call gaze.startAnswer() / gaze.stopAnswer().
 *
 *   import useGaze from "../gaze/useGaze";
 *   import GazeWidget from "../gaze/GazeWidget";
 *   const gaze = useGaze();
 *   <GazeWidget gaze={gaze} />
 *
 * If the camera fails, the widget explains why and the interview carries on without it.
 */

import { useState } from "react";
import { deviceLabel } from "../devices";

const C = {
  indigo: "#2B1A7F",
  pink: "#E0245E",
  mint: "#0E9F6E",
  amber: "#D98E04",
  grey: "#8A8FA3",
  ink: "#1F2233",
  lavender: "#EFEBFB",
};

const styles = {
  box: {
    width: 240,
    background: C.lavender,
    borderRadius: 12,
    padding: 12,
    fontFamily: "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
    color: C.ink,
    boxSizing: "border-box",
  },
  videoWrap: {
    position: "relative",
    width: "100%",
    aspectRatio: "4 / 3",
    borderRadius: 8,
    overflow: "hidden",
    background: "#D9D4F2",
  },
  video: {
    width: "100%",
    height: "100%",
    objectFit: "cover",
    transform: "scaleX(-1)", // mirror so it feels natural
    display: "block",
  },
  overlay: {
    position: "absolute",
    inset: 0,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    textAlign: "center",
    padding: 12,
    fontSize: 13,
    fontWeight: 600,
    color: "#fff",
    background: "rgba(43, 26, 127, 0.72)",
  },
  row: { display: "flex", alignItems: "center", gap: 8, marginTop: 10, fontSize: 14 },
  dot: (color) => ({ width: 10, height: 10, borderRadius: "50%", background: color, flexShrink: 0 }),
  button: {
    marginTop: 10,
    width: "100%",
    padding: "8px 10px",
    border: "none",
    borderRadius: 8,
    background: C.indigo,
    color: "#fff",
    fontSize: 13,
    fontWeight: 600,
    cursor: "pointer",
  },
  note: { marginTop: 8, fontSize: 12, lineHeight: 1.4, color: "#4B5068" },
  select: {
    marginTop: 10,
    width: "100%",
    padding: "6px 8px",
    borderRadius: 8,
    border: "1px solid #DCD4F7",
    fontSize: 12,
    background: "#fff",
    color: C.ink,
  },
  error: { marginTop: 8, fontSize: 12, lineHeight: 1.4, color: C.pink },
};

export default function GazeWidget({ gaze }) {
  const [busy, setBusy] = useState(false);
  if (!gaze) return null;

  const { videoRef, status, error, errorKind, hasBaseline, live, cameras = [], cameraId } = gaze;
  const cameraOn = status === "ready" || status === "calibrating";

  const turnOn = async () => {
    setBusy(true);
    await gaze.start();
    setBusy(false);
  };

  const checkEyeLine = async () => {
    setBusy(true);
    await gaze.captureBaseline();
    setBusy(false);
  };

  // status line
  let dotColor = C.grey;
  let line = "Camera is off";
  if (status === "loading") line = "Starting camera…";
  if (status === "denied" || status === "error") {
    dotColor = C.pink;
    line = errorKind === "model" ? "Eye tracking not set up" : "Camera unavailable";
  }
  if (status === "calibrating") {
    dotColor = C.amber;
    line = "Hold still…";
  }
  if (status === "ready") {
    if (!live.facePresent) {
      dotColor = C.amber;
      line = "No face found";
    } else if (live.answering && live.eyeContactPct !== null) {
      dotColor = live.eyeContactPct >= 60 ? C.mint : C.amber;
      line = `Eye contact ${live.eyeContactPct}%`;
    } else {
      dotColor = live.looking ? C.mint : C.amber;
      line = live.looking ? "Looking at the camera" : "Looking away";
    }
  }

  return (
    <div style={styles.box} aria-live="polite">
      <div style={styles.videoWrap}>
        <video ref={videoRef} style={styles.video} muted playsInline autoPlay />
        {!cameraOn && (
          <div style={styles.overlay}>
            {status === "loading" ? "Starting camera…" : "Camera preview stays on this laptop"}
          </div>
        )}
        {status === "calibrating" && <div style={styles.overlay}>Look straight at the camera for 3 seconds</div>}
      </div>

      <div style={styles.row}>
        <span style={styles.dot(dotColor)} />
        <span style={{ fontWeight: 600 }}>{line}</span>
      </div>

      {cameras.length > 1 && (
        <label>
          <span style={{ display: "block", marginTop: 10, fontSize: 12, fontWeight: 600 }}>Camera</span>
          <select
            style={{ ...styles.select, marginTop: 4 }}
            value={cameraId || ""}
            onChange={(e) => gaze.selectCamera(e.target.value)}
            disabled={busy || status === "loading" || status === "calibrating"}
          >
            {!cameraId && <option value="">Choose a camera</option>}
            {cameras.map((cam, i) => (
              <option key={cam.deviceId} value={cam.deviceId}>
                {deviceLabel(cam, i, "videoinput")}
              </option>
            ))}
          </select>
        </label>
      )}

      {(status === "idle" || status === "denied" || status === "error") && (
        <button style={styles.button} onClick={turnOn} disabled={busy}>
          {status === "idle" ? "Turn on camera" : "Try camera again"}
        </button>
      )}

      {status === "ready" && !hasBaseline && (
        <>
          <button style={{ ...styles.button, background: C.pink }} onClick={checkEyeLine} disabled={busy}>
            Check my eye line (3 s)
          </button>
          <p style={styles.note}>Look at the camera while it checks. This makes eye-contact scores fair for your setup.</p>
        </>
      )}

      {status === "ready" && hasBaseline && (
        <p style={styles.note}>Eye line saved. Answer naturally — glancing away to think is fine.</p>
      )}

      {error && <p style={styles.error}>{error}</p>}
      {(status === "denied" || status === "error") && (
        <p style={styles.note}>You can still answer every question. Confidence will use your voice only.</p>
      )}
    </div>
  );
}
