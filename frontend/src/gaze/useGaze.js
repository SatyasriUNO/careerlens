/*
 * useGaze.js  —  Member 4 (GazeGuard-lite)
 *
 * Tracks the student's eye line through the webcam with MediaPipe Face Landmarker.
 * Video never leaves the browser. Only these numbers are sent per answer:
 *   { eye_contact_pct, look_away_count, face_present_pct, tracking_quality, duration_s }
 *
 * How to use inside a page (Member 1, InterviewRoom.jsx):
 *   const gaze = useGaze();
 *   <GazeWidget gaze={gaze} />
 *   when a question appears:   gaze.startAnswer();
 *   when the answer is sent:   const g = gaze.stopAnswer();   // object or null
 *                              if (g) formData.append("gaze", JSON.stringify(g));
 *
 * Camera choice: the hook avoids virtual cameras (OBS, Snap...) and remembers the camera
 * the student picks in GazeWidget (gaze.cameras, gaze.cameraId, gaze.selectCamera(id)).
 *
 * Offline requirement: the MediaPipe files are served from frontend/public/mediapipe/
 * (see README for the copy + download commands).
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { FaceLandmarker, FilesetResolver } from "@mediapipe/tasks-vision";
import { chooseDeviceId, describeMediaError, isVirtual, listDevices, openMedia, preferredDeviceId, saveDeviceId, savedDeviceId } from "../devices";

const WASM_PATH = "/mediapipe/wasm";
const MODEL_PATH = "/mediapipe/face_landmarker.task";

// Tune these on Day 2 with GazeDebug.jsx. All values are ratios (0 to 1), not degrees.
export const GAZE_SETTINGS = {
  irisH: 0.08,          // allowed sideways eye movement from baseline
  irisV: 0.14,          // allowed up/down eye movement from baseline
  yaw: 0.12,            // allowed head turn (left/right) from baseline
  pitch: 0.1,           // allowed head tilt (up/down) from baseline
  lookAwayMs: 1000,     // looking away this long counts as one look-away
  returnMs: 300,        // must look back this long before the next look-away can count
  blinkOpenness: 0.15,  // eye height / eye width below this = blink (frame ignored)
  frameMs: 66,          // process about 15 frames per second (saves CPU for the LLM)
  smoothing: 0.4,       // 0 = very smooth/slow, 1 = raw/jittery
  baselineMs: 3000,     // length of the "look at the camera" check
};

// Face landmark numbers (MediaPipe 478-point face mesh)
const EYE_1 = { cornerA: 33, cornerB: 133, upper: 159, lower: 145 };
const EYE_2 = { cornerA: 263, cornerB: 362, upper: 386, lower: 374 };
const IRIS_CENTRES = [468, 473];
const NOSE_TIP = 1;
const CHEEK_1 = 234;
const CHEEK_2 = 454;
const FOREHEAD = 10;
const CHIN = 152;

const DEFAULT_BASELINE = { h: 0.5, v: 0.45, yaw: 0.5, pitch: 0.5 };

// ---------- model loading (shared, loaded once per browser tab)
const SETUP_HINT = "In the frontend folder run:  npm run setup-mediapipe  then restart npm run dev and reload this page.";

function setupError(message) {
  const err = new Error(`${message} ${SETUP_HINT}`);
  err.name = "ModelFileError";
  return err;
}

// Check the two offline files exist and are real (not the web page the dev server
// sends back when a file is missing). Returns the model bytes so they load only once.
async function fetchModelFiles() {
  let wasm;
  try {
    wasm = await fetch(`${WASM_PATH}/vision_wasm_internal.js`, { cache: "no-store" });
  } catch {
    throw setupError("Could not read the face-tracking files.");
  }
  const wasmType = wasm.headers.get("content-type") || "";
  if (!wasm.ok || wasmType.includes("text/html")) {
    throw setupError("Face-tracking files are missing (public/mediapipe/wasm).");
  }

  let model;
  try {
    model = await fetch(MODEL_PATH, { cache: "no-store" });
  } catch {
    throw setupError("Could not read the face-tracking model.");
  }
  const bytes = new Uint8Array(await model.arrayBuffer());
  if (!model.ok || !looksLikeModel(bytes)) {
    throw setupError(
      bytes.length < 1000000
        ? "The face-tracking model file is missing or incomplete (public/mediapipe/face_landmarker.task)."
        : "The face-tracking model file is damaged (public/mediapipe/face_landmarker.task)."
    );
  }
  return bytes;
}

// A .task file is model data with a zip archive at the END: look for the zip
// "end of archive" marker (PK 05 06) in the last 64 KB.
function looksLikeModel(bytes) {
  if (bytes.length < 1000000) return false;
  const stop = Math.max(0, bytes.length - 66000);
  for (let i = bytes.length - 22; i >= stop; i -= 1) {
    if (bytes[i] === 0x50 && bytes[i + 1] === 0x4b && bytes[i + 2] === 0x05 && bytes[i + 3] === 0x06) return true;
  }
  return false;
}

let landmarkerPromise = null;

function loadLandmarker() {
  if (!landmarkerPromise) {
    landmarkerPromise = (async () => {
      const modelBytes = await fetchModelFiles();
      const fileset = await FilesetResolver.forVisionTasks(WASM_PATH);
      const create = (delegate) =>
        FaceLandmarker.createFromOptions(fileset, {
          baseOptions: { modelAssetBuffer: modelBytes, delegate },
          runningMode: "VIDEO",
          numFaces: 1,
        });
      try {
        return await create("GPU");
      } catch {
        try {
          return await create("CPU");
        } catch (e) {
          const err = new Error(`The face tracker could not start. ${SETUP_HINT}`);
          err.name = "ModelFileError";
          err.cause = e;
          throw err;
        }
      }
    })();
    landmarkerPromise.catch(() => {
      landmarkerPromise = null; // allow a retry after a failure
    });
  }
  return landmarkerPromise;
}

// ---------- geometry helpers
const distance = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);

function measureEye(lm, eye) {
  const a = lm[eye.cornerA];
  const b = lm[eye.cornerB];
  const left = a.x < b.x ? a : b;
  const right = a.x < b.x ? b : a;
  const middle = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };

  // Pick whichever iris centre sits inside this eye (works whatever the mirror order is)
  let iris = lm[IRIS_CENTRES[0]];
  if (distance(lm[IRIS_CENTRES[1]], middle) < distance(iris, middle)) iris = lm[IRIS_CENTRES[1]];

  const width = right.x - left.x;
  if (width <= 0) return null;
  const upper = lm[eye.upper];
  const lower = lm[eye.lower];
  const height = Math.max(0, lower.y - upper.y);

  return {
    h: (iris.x - left.x) / width,
    v: height > 0 ? (iris.y - upper.y) / height : 0.5,
    open: height / width,
  };
}

function measureFrame(lm) {
  if (!lm || lm.length < 478) return null;
  const e1 = measureEye(lm, EYE_1);
  const e2 = measureEye(lm, EYE_2);
  if (!e1 || !e2) return null;

  const cheekLeftX = Math.min(lm[CHEEK_1].x, lm[CHEEK_2].x);
  const faceWidth = Math.abs(lm[CHEEK_2].x - lm[CHEEK_1].x);
  const faceHeight = lm[CHIN].y - lm[FOREHEAD].y;
  if (faceWidth <= 0 || faceHeight <= 0) return null;

  return {
    h: (e1.h + e2.h) / 2,
    v: (e1.v + e2.v) / 2,
    open: (e1.open + e2.open) / 2,
    yaw: (lm[NOSE_TIP].x - cheekLeftX) / faceWidth,
    pitch: (lm[NOSE_TIP].y - lm[FOREHEAD].y) / faceHeight,
  };
}

function median(values) {
  const sorted = [...values].sort((x, y) => x - y);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

function isLookingAtCamera(m, base) {
  const s = GAZE_SETTINGS;
  return (
    Math.abs(m.h - base.h) <= s.irisH &&
    Math.abs(m.v - base.v) <= s.irisV &&
    Math.abs(m.yaw - base.yaw) <= s.yaw &&
    Math.abs(m.pitch - base.pitch) <= s.pitch
  );
}

function newAnswerCounters() {
  return { start: performance.now(), totalFrames: 0, faceFrames: 0, validFrames: 0, lookingFrames: 0, lookAways: 0 };
}

function newAwayState() {
  return { looking: true, awaySince: null, backSince: null, counted: false };
}

// ---------- the hook
export default function useGaze() {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const landmarkerRef = useRef(null);
  const rafRef = useRef(0);
  const lastProcessRef = useRef(0);
  const lastVideoTimeRef = useRef(-1);
  const smoothRef = useRef(null);
  const baselineRef = useRef(null);
  const baselineSamplesRef = useRef(null);
  const answerRef = useRef(null);
  const awayRef = useRef(newAwayState());
  const statusRef = useRef("idle");
  const lastLiveUpdateRef = useRef(0);
  const debugRef = useRef({});

  const [status, setStatusState] = useState("idle"); // idle | loading | ready | calibrating | denied | error
  const [error, setError] = useState("");
  const [errorKind, setErrorKind] = useState(""); // "" | "camera" | "model"
  const [hasBaseline, setHasBaseline] = useState(false);
  const [live, setLive] = useState({ facePresent: false, looking: false, eyeContactPct: null, answering: false });
  const [cameras, setCameras] = useState([]);
  const [cameraId, setCameraId] = useState(null);
  const [cameraLabel, setCameraLabel] = useState("");

  const setStatus = useCallback((value) => {
    statusRef.current = value;
    setStatusState(value);
  }, []);

  // ----- look-away state machine
  const updateAwayState = (looking, now) => {
    const st = awayRef.current;
    if (looking) {
      st.awaySince = null;
      if (!st.looking) {
        if (st.backSince === null) st.backSince = now;
        if (now - st.backSince >= GAZE_SETTINGS.returnMs) {
          st.looking = true;
          st.backSince = null;
          st.counted = false;
        }
      }
    } else {
      st.backSince = null;
      if (st.awaySince === null) st.awaySince = now;
      if (!st.counted && now - st.awaySince >= GAZE_SETTINGS.lookAwayMs) {
        st.looking = false;
        st.counted = true;
        if (answerRef.current) answerRef.current.lookAways += 1;
      }
    }
  };

  // ----- one processed frame
  const processFrame = (m, now) => {
    const answer = answerRef.current;
    if (answer) answer.totalFrames += 1;

    let facePresent = false;
    let looking = false;

    if (!m) {
      smoothRef.current = null;
      updateAwayState(false, now);
    } else {
      facePresent = true;
      if (answer) answer.faceFrames += 1;

      if (m.open >= GAZE_SETTINGS.blinkOpenness) {
        // smooth the measurements
        const a = GAZE_SETTINGS.smoothing;
        const prev = smoothRef.current;
        const s = prev
          ? {
              h: prev.h + a * (m.h - prev.h),
              v: prev.v + a * (m.v - prev.v),
              yaw: prev.yaw + a * (m.yaw - prev.yaw),
              pitch: prev.pitch + a * (m.pitch - prev.pitch),
            }
          : { h: m.h, v: m.v, yaw: m.yaw, pitch: m.pitch };
        smoothRef.current = s;

        if (baselineSamplesRef.current) baselineSamplesRef.current.push(s);

        looking = isLookingAtCamera(s, baselineRef.current || DEFAULT_BASELINE);
        updateAwayState(looking, now);
        if (answer) {
          answer.validFrames += 1;
          if (looking) answer.lookingFrames += 1;
        }
        debugRef.current = { ...s, open: m.open, looking, baseline: baselineRef.current };
      } else {
        // blink: keep the previous looking state, do not count the frame
        looking = awayRef.current.looking;
        debugRef.current = { ...debugRef.current, open: m.open, blink: true };
      }
    }

    if (!m) debugRef.current = { face: false };

    // update the on-screen numbers about 4 times a second
    if (now - lastLiveUpdateRef.current > 250) {
      lastLiveUpdateRef.current = now;
      const pct = answer && answer.validFrames > 0 ? Math.round((answer.lookingFrames / answer.validFrames) * 100) : null;
      setLive({ facePresent, looking, eyeContactPct: pct, answering: Boolean(answer) });
    }
  };

  // ----- frame loop (always reads the newest processFrame through a ref)
  const processRef = useRef(processFrame);
  processRef.current = processFrame;

  const tick = useCallback(() => {
    rafRef.current = requestAnimationFrame(tick);
    const video = videoRef.current;
    const landmarker = landmarkerRef.current;
    if (!video || !landmarker) return;

    if (streamRef.current && video.srcObject !== streamRef.current) {
      video.srcObject = streamRef.current; // re-attach if the widget re-mounted
      video.play().catch(() => {});
    }
    if (video.readyState < 2) return;

    const now = performance.now();
    if (now - lastProcessRef.current < GAZE_SETTINGS.frameMs) return;
    if (video.currentTime === lastVideoTimeRef.current) return;
    lastProcessRef.current = now;
    lastVideoTimeRef.current = video.currentTime;

    let result;
    try {
      result = landmarker.detectForVideo(video, now);
    } catch {
      return;
    }
    const lm = result && result.faceLandmarks && result.faceLandmarks[0];
    processRef.current(lm ? measureFrame(lm) : null, now);
  }, []);

  // ----- public actions
  const stopStream = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (videoRef.current) videoRef.current.srcObject = null;
  };

  const stop = useCallback(() => {
    cancelAnimationFrame(rafRef.current);
    rafRef.current = 0;
    stopStream();
    answerRef.current = null;
    setStatus("idle");
  }, [setStatus]);

  const refreshCameras = useCallback(async () => {
    const list = await listDevices("videoinput");
    setCameras(list);
    return list;
  }, []);

  // Open one camera and show it in the <video>. Throws the browser error on failure.
  const openCamera = async (deviceId) => {
    stopStream();
    const stream = await openMedia("videoinput", deviceId);
    streamRef.current = stream;
    const track = stream.getVideoTracks()[0];
    const settings = track && track.getSettings ? track.getSettings() : {};
    setCameraId(settings.deviceId || deviceId || null);
    setCameraLabel(track ? track.label : "");
    if (videoRef.current) {
      videoRef.current.srcObject = stream;
      await videoRef.current.play().catch(() => {});
    }
    return track;
  };

  const start = useCallback(async () => {
    if (["loading", "ready", "calibrating"].includes(statusRef.current)) return true;
    setError("");
    setErrorKind("");
    setStatus("loading");
    try {
      // 1. open the saved / best camera (labels may be hidden before the first permission)
      let list = await refreshCameras();
      let track = await openCamera(chooseDeviceId("videoinput", list));

      // 2. labels are visible now: if we landed on a virtual camera, switch to a real one
      list = await refreshCameras();
      const userPicked = Boolean(savedDeviceId("videoinput"));
      if (track && isVirtual(track.label) && !userPicked) {
        const real = preferredDeviceId(list);
        if (real) track = await openCamera(real);
      }

      landmarkerRef.current = await loadLandmarker();
      setStatus("ready");
      if (!rafRef.current) rafRef.current = requestAnimationFrame(tick);
      return true;
    } catch (e) {
      stopStream();
      if (e && e.name === "ModelFileError") {
        setStatus("error");
        setErrorKind("model");
        setError(e.message);
        if (e.cause) console.error("MediaPipe error:", e.cause);
        return false;
      }
      const denied = e && (e.name === "NotAllowedError" || e.name === "SecurityError");
      setStatus(denied ? "denied" : "error");
      setErrorKind("camera");
      setError(e && e.name ? describeMediaError(e, "videoinput") : (e && e.message) || "The camera could not start.");
      refreshCameras();
      return false;
    }
  }, [setStatus, tick, refreshCameras]);

  // Switch to another camera chosen in the widget. The eye-line check must be redone.
  const selectCamera = useCallback(async (deviceId) => {
    saveDeviceId("videoinput", deviceId);
    setCameraId(deviceId);
    if (!["ready", "calibrating", "error"].includes(statusRef.current)) return;
    setError("");
    setStatus("loading");
    try {
      await openCamera(deviceId);
      baselineRef.current = null;
      setHasBaseline(false);
      smoothRef.current = null;
      if (!landmarkerRef.current) landmarkerRef.current = await loadLandmarker();
      setStatus("ready");
      if (!rafRef.current) rafRef.current = requestAnimationFrame(tick);
    } catch (e) {
      stopStream();
      setStatus("error");
      setErrorKind(e && e.name === "ModelFileError" ? "model" : "camera");
      setError(e && e.name === "ModelFileError" ? e.message : describeMediaError(e, "videoinput"));
    }
  }, [setStatus, tick]);

  // keep the camera list up to date when devices are plugged in or out
  useEffect(() => {
    const md = navigator.mediaDevices;
    if (!md || !md.addEventListener) return undefined;
    const onChange = () => refreshCameras();
    md.addEventListener("devicechange", onChange);
    return () => md.removeEventListener("devicechange", onChange);
  }, [refreshCameras]);

  const captureBaseline = useCallback(async () => {
    if (statusRef.current !== "ready") return false;
    setStatus("calibrating");
    baselineSamplesRef.current = [];
    await new Promise((resolve) => setTimeout(resolve, GAZE_SETTINGS.baselineMs));
    const samples = baselineSamplesRef.current || [];
    baselineSamplesRef.current = null;

    if (samples.length < 10) {
      setStatus("ready");
      setError("Your face was not clear enough. Face the light, sit 50–70 cm away, and try again.");
      return false;
    }
    baselineRef.current = {
      h: median(samples.map((s) => s.h)),
      v: median(samples.map((s) => s.v)),
      yaw: median(samples.map((s) => s.yaw)),
      pitch: median(samples.map((s) => s.pitch)),
    };
    setHasBaseline(true);
    setError("");
    setStatus("ready");
    return true;
  }, [setStatus]);

  const startAnswer = useCallback(() => {
    answerRef.current = newAnswerCounters();
    awayRef.current = newAwayState();
  }, []);

  const stopAnswer = useCallback(() => {
    const a = answerRef.current;
    answerRef.current = null;
    if (!a || statusRef.current !== "ready" || a.totalFrames < 5) return null;

    const durationS = (performance.now() - a.start) / 1000;
    const facePct = (a.faceFrames / a.totalFrames) * 100;
    const eyePct = a.validFrames > 0 ? (a.lookingFrames / a.validFrames) * 100 : 0;
    const good = Boolean(baselineRef.current) && facePct >= 80 && a.validFrames >= 10;

    return {
      eye_contact_pct: Math.round(eyePct),
      look_away_count: a.lookAways,
      face_present_pct: Math.round(facePct),
      tracking_quality: good ? "good" : "low",
      duration_s: Math.round(durationS * 10) / 10,
    };
  }, []);

  // stop the camera when the page using this hook closes
  useEffect(() => () => stop(), [stop]);

  return {
    videoRef,
    status,
    error,
    errorKind,
    hasBaseline,
    live,
    cameras,
    cameraId,
    cameraLabel,
    selectCamera,
    start,
    stop,
    captureBaseline,
    startAnswer,
    stopAnswer,
    debugRef,
  };
}
