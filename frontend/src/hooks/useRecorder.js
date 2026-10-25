/*
 * useRecorder.js — records one spoken answer from the microphone as a webm audio blob.
 *
 *   const rec = useRecorder();
 *   rec.start(); rec.stop(); rec.reset();
 *   rec.blob, rec.seconds, rec.recording, rec.error, rec.warning
 *   rec.level          0..1 live loudness while recording (for the meter)
 *   rec.mics, rec.micId, rec.selectMic(id), rec.refreshMics()
 *
 * Avoids virtual microphones, remembers the student's choice, and warns when the
 * recording was silent (wrong microphone selected) before it is sent to the backend.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { chooseDeviceId, describeMediaError, isVirtual, listDevices, openMedia, preferredDeviceId, saveDeviceId, savedDeviceId } from "../devices";

const MIN_BLOB_BYTES = 2000;   // smaller than this = nothing was recorded
const SILENCE_PEAK = 0.04;     // loudest moment below this = microphone heard nothing
const MIN_SECONDS = 2;

function pickMimeType() {
  if (typeof MediaRecorder === "undefined") return "";
  const options = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus"];
  return options.find((t) => MediaRecorder.isTypeSupported(t)) || "";
}

export default function useRecorder() {
  const recorderRef = useRef(null);
  const streamRef = useRef(null);
  const chunksRef = useRef([]);
  const timerRef = useRef(null);
  const audioCtxRef = useRef(null);
  const meterRafRef = useRef(0);
  const peakRef = useRef(0);
  const secondsRef = useRef(0);

  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [blob, setBlob] = useState(null);
  const [error, setError] = useState("");
  const [warning, setWarning] = useState("");
  const [level, setLevel] = useState(0);
  const [mics, setMics] = useState([]);
  const [micId, setMicId] = useState(() => savedDeviceId("audioinput"));

  const refreshMics = useCallback(async () => {
    const list = await listDevices("audioinput");
    setMics(list);
    return list;
  }, []);

  useEffect(() => {
    refreshMics();
    const md = navigator.mediaDevices;
    if (!md || !md.addEventListener) return undefined;
    md.addEventListener("devicechange", refreshMics);
    return () => md.removeEventListener("devicechange", refreshMics);
  }, [refreshMics]);

  const stopMeter = () => {
    cancelAnimationFrame(meterRafRef.current);
    meterRafRef.current = 0;
    if (audioCtxRef.current) {
      audioCtxRef.current.close().catch(() => {});
      audioCtxRef.current = null;
    }
    setLevel(0);
  };

  const releaseMic = () => {
    clearInterval(timerRef.current);
    stopMeter();
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
  };

  const startMeter = (stream) => {
    try {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      if (!Ctx) return;
      const ctx = new Ctx();
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 1024;
      ctx.createMediaStreamSource(stream).connect(analyser);
      audioCtxRef.current = ctx;
      const data = new Uint8Array(analyser.fftSize);
      let lastUpdate = 0;
      const loop = (now) => {
        analyser.getByteTimeDomainData(data);
        let sum = 0;
        for (let i = 0; i < data.length; i += 1) {
          const v = (data[i] - 128) / 128;
          sum += v * v;
        }
        const rms = Math.sqrt(sum / data.length);
        const value = Math.min(1, rms * 4);
        peakRef.current = Math.max(peakRef.current, value);
        if (now - lastUpdate > 80) {
          lastUpdate = now;
          setLevel(value);
        }
        meterRafRef.current = requestAnimationFrame(loop);
      };
      meterRafRef.current = requestAnimationFrame(loop);
    } catch {
      /* meter is optional */
    }
  };

  const start = useCallback(async () => {
    setError("");
    setWarning("");
    setBlob(null);
    setSeconds(0);
    secondsRef.current = 0;
    peakRef.current = 0;
    try {
      if (typeof MediaRecorder === "undefined") {
        const e = new Error("This browser cannot record audio. Use Chrome or Edge.");
        e.name = "NotSupportedError";
        throw e;
      }
      let list = await refreshMics();
      let stream = await openMedia("audioinput", micId || chooseDeviceId("audioinput", list));

      // labels are visible now: avoid a virtual microphone unless the student chose it
      list = await refreshMics();
      const track = stream.getAudioTracks()[0];
      if (track && isVirtual(track.label) && !savedDeviceId("audioinput")) {
        const real = preferredDeviceId(list);
        if (real) {
          stream.getTracks().forEach((t) => t.stop());
          stream = await openMedia("audioinput", real);
        }
      }
      const active = stream.getAudioTracks()[0];
      const settings = active && active.getSettings ? active.getSettings() : {};
      if (settings.deviceId) setMicId(settings.deviceId);

      streamRef.current = stream;
      startMeter(stream);

      const mimeType = pickMimeType();
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      chunksRef.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.onstop = () => {
        const type = recorder.mimeType || "audio/webm";
        const result = new Blob(chunksRef.current, { type });
        releaseMic();
        setRecording(false);
        if (result.size < MIN_BLOB_BYTES || secondsRef.current < MIN_SECONDS) {
          setBlob(null);
          setError("The recording was empty or too short. Record again and speak for at least 5 seconds.");
          return;
        }
        if (peakRef.current < SILENCE_PEAK) {
          setWarning("We could hardly hear you. Check that the right microphone is selected below, then record again — or submit anyway.");
        }
        setBlob(result);
      };
      recorderRef.current = recorder;
      recorder.start(); // one chunk at the end gives the cleanest webm file
      setRecording(true);
      const began = Date.now();
      timerRef.current = setInterval(() => {
        const s = Math.floor((Date.now() - began) / 1000);
        secondsRef.current = s;
        setSeconds(s);
      }, 250);
    } catch (e) {
      releaseMic();
      setRecording(false);
      setError(e && e.name ? describeMediaError(e, "audioinput") : "The microphone could not start. Type your answer instead.");
    }
  }, [micId, refreshMics]);

  const stop = useCallback(() => {
    const recorder = recorderRef.current;
    if (recorder && recorder.state !== "inactive") recorder.stop();
  }, []);

  const reset = useCallback(() => {
    const recorder = recorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      recorder.onstop = null; // throw this recording away
      recorder.ondataavailable = null;
      recorder.stop();
    }
    recorderRef.current = null;
    releaseMic();
    setRecording(false);
    setBlob(null);
    setSeconds(0);
    setError("");
    setWarning("");
  }, []);

  const selectMic = useCallback((deviceId) => {
    saveDeviceId("audioinput", deviceId);
    setMicId(deviceId);
  }, []);

  useEffect(() => () => {
    const recorder = recorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      recorder.onstop = null;
      recorder.stop();
    }
    releaseMic();
  }, []);

  return { recording, seconds, blob, error, warning, level, mics, micId, selectMic, refreshMics, start, stop, reset };
}
