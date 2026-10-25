/*
 * devices.js — picks the real camera / microphone and explains errors in plain words.
 *
 * Windows laptops often have "virtual" devices (OBS Virtual Camera, Snap Camera, NVIDIA
 * Broadcast, VB-Audio cable...). Browsers sometimes choose one of these by default, which
 * gives a black picture or a silent recording. These helpers prefer the built-in devices
 * and remember the student's choice.
 */

const VIRTUAL_HINTS = [
  "virtual", "obs", "snap camera", "manycam", "xsplit", "droidcam", "iriun", "camo",
  "nvidia broadcast", "epoccam", "vcam", "splitcam", "streamlabs", "e2esoft", "youcam",
  "voicemeeter", "vb-audio", "cable output", "stereo mix",
];

const BUILT_IN_HINTS = /integrated|built-in|internal|facetime|hd webcam|hd camera|hd user facing|microphone array|realtek|intel|laptop/i;

const STORAGE_KEYS = { videoinput: "careerlens-camera", audioinput: "careerlens-mic" };

export function isVirtual(label = "") {
  const text = label.toLowerCase();
  return VIRTUAL_HINTS.some((hint) => text.includes(hint));
}

/** All devices of one kind ("videoinput" or "audioinput"). Labels are empty until permission is given. */
export async function listDevices(kind) {
  if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) return [];
  try {
    const all = await navigator.mediaDevices.enumerateDevices();
    return all.filter((d) => d.kind === kind && d.deviceId && d.deviceId !== "communications");
  } catch {
    return [];
  }
}

export function savedDeviceId(kind) {
  try {
    return localStorage.getItem(STORAGE_KEYS[kind]) || null;
  } catch {
    return null;
  }
}

export function saveDeviceId(kind, deviceId) {
  try {
    if (deviceId) localStorage.setItem(STORAGE_KEYS[kind], deviceId);
    else localStorage.removeItem(STORAGE_KEYS[kind]);
  } catch {
    /* storage blocked: the choice just is not remembered */
  }
}

/** Best guess: a built-in device, else any non-virtual device, else the first one. */
export function preferredDeviceId(devices) {
  const physical = devices.filter((d) => d.label && !isVirtual(d.label));
  const builtIn = physical.find((d) => d.deviceId !== "default" && BUILT_IN_HINTS.test(d.label));
  const firstReal = physical.find((d) => d.deviceId !== "default") || physical[0];
  const chosen = builtIn || firstReal || null;
  return chosen ? chosen.deviceId : null;
}

/** Saved choice if that device still exists, otherwise the preferred device. */
export function chooseDeviceId(kind, devices) {
  const saved = savedDeviceId(kind);
  if (saved && devices.some((d) => d.deviceId === saved)) return saved;
  return preferredDeviceId(devices);
}

export function deviceLabel(device, index, kind) {
  if (device.label) return device.label + (isVirtual(device.label) ? " (virtual)" : "");
  return `${kind === "videoinput" ? "Camera" : "Microphone"} ${index + 1}`;
}

/** Plain-language explanation of a getUserMedia error. */
export function describeMediaError(error, kind) {
  const thing = kind === "videoinput" ? "camera" : "microphone";
  const name = (error && error.name) || "";
  if (name === "NotAllowedError" || name === "SecurityError" || name === "PermissionDeniedError") {
    return `The browser blocked the ${thing}. Click the ${thing} icon in the address bar, choose Allow, then try again. ` +
      `Also check Windows Settings → Privacy & security → ${thing === "camera" ? "Camera" : "Microphone"} → allow apps and desktop apps.`;
  }
  if (name === "NotReadableError" || name === "TrackStartError" || name === "AbortError") {
    return `Could not start the ${thing}. Another app is probably using it (Zoom, Teams, Meet in another tab, the Windows Camera app, OBS). ` +
      `Close those apps, then try again — or pick a different ${thing} from the list.`;
  }
  if (name === "NotFoundError" || name === "DevicesNotFoundError") {
    return `No ${thing} was found. Plug one in or turn it on (some laptops have a camera key or privacy shutter), then try again.`;
  }
  if (name === "OverconstrainedError" || name === "ConstraintNotSatisfiedError") {
    return `The selected ${thing} is not available any more. Pick another one from the list.`;
  }
  return `The ${thing} could not start${error && error.message ? `: ${error.message}` : "."}`;
}

/**
 * Open a camera or microphone, trying simpler settings when a strict request fails.
 * Stops immediately on "permission denied" (retrying cannot help).
 */
export async function openMedia(kind, deviceId) {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    const err = new Error("This browser cannot open the camera or microphone. Use Chrome or Edge.");
    err.name = "NotSupportedError";
    throw err;
  }
  const attempts = [];
  if (kind === "videoinput") {
    if (deviceId) {
      attempts.push({ video: { deviceId: { exact: deviceId }, width: { ideal: 640 }, height: { ideal: 480 } }, audio: false });
      attempts.push({ video: { deviceId: { exact: deviceId } }, audio: false });
    }
    attempts.push({ video: { width: { ideal: 640 }, height: { ideal: 480 } }, audio: false });
    attempts.push({ video: true, audio: false });
  } else {
    const clean = { echoCancellation: true, noiseSuppression: true, autoGainControl: true };
    if (deviceId) {
      attempts.push({ audio: { ...clean, deviceId: { exact: deviceId } }, video: false });
      attempts.push({ audio: { deviceId: { exact: deviceId } }, video: false });
    }
    attempts.push({ audio: clean, video: false });
    attempts.push({ audio: true, video: false });
  }

  let lastError = null;
  for (const constraints of attempts) {
    try {
      return await navigator.mediaDevices.getUserMedia(constraints);
    } catch (e) {
      lastError = e;
      if (e && (e.name === "NotAllowedError" || e.name === "SecurityError")) break;
    }
  }
  throw lastError;
}
