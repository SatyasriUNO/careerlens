/*
 * api.js — the ONLY file that talks to the backend.
 * Settings come from frontend/.env (see .env.example):
 *   VITE_API_URL   default http://localhost:8000
 *   VITE_USE_MOCKS "true" to use fake data with no backend
 */
import { mockAnswer, mockHealth, mockHistory, mockQuestions, mockReport, mockResume, mockShield } from "./mocks";

export const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";
export const USE_MOCKS = import.meta.env.VITE_USE_MOCKS === "true";

const wait = (ms) => new Promise((r) => setTimeout(r, ms));

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(`${API_URL}${path}`, options);
  } catch {
    throw new Error("Cannot reach the CareerLens backend. Start it with: uvicorn main:app --port 8000");
  }
  let data = null;
  try {
    data = await response.json();
  } catch {
    /* empty or non-JSON body */
  }
  if (!response.ok) {
    const detail = data && data.detail;
    throw new Error(typeof detail === "string" ? detail : `Request failed (${response.status}).`);
  }
  return data;
}

const postJson = (path, body) =>
  request(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export async function getHealth() {
  if (USE_MOCKS) return mockHealth;
  return request("/api/health");
}

export async function analyzeResume(file, role, jdText) {
  if (USE_MOCKS) {
    await wait(900);
    return { ...mockResume, role };
  }
  const form = new FormData();
  form.append("file", file);
  form.append("role", role);
  form.append("jd_text", jdText || "");
  return request("/api/resume/analyze", { method: "POST", body: form });
}

export async function startInterview(resumeId, role, consent) {
  if (USE_MOCKS) {
    await wait(700);
    return { session_id: "s_001", question: mockQuestions[0] };
  }
  return postJson("/api/interview/start", { resume_id: resumeId, role, consent });
}

/**
 * Send one answer. Give either audioBlob (voice) or typedText (typed).
 * gaze is the object from useGaze().stopAnswer() or null.
 */
export async function submitAnswer({ sessionId, questionId, audioBlob, typedText, gaze }) {
  if (USE_MOCKS) {
    await wait(1200);
    return mockAnswer(questionId, audioBlob ? "voice" : "typed", gaze);
  }
  const form = new FormData();
  form.append("session_id", sessionId);
  form.append("question_id", questionId);
  if (audioBlob) form.append("audio", audioBlob, "answer.webm");
  if (typedText) form.append("typed_text", typedText);
  if (gaze) form.append("gaze", JSON.stringify(gaze));
  return request("/api/interview/answer", { method: "POST", body: form });
}

export async function finishInterview(sessionId) {
  if (USE_MOCKS) {
    await wait(1000);
    return mockReport;
  }
  return postJson("/api/interview/finish", { session_id: sessionId });
}

export async function getShieldStatus() {
  if (USE_MOCKS) return mockShield;
  return request("/api/shield/status");
}

export async function getHistory() {
  if (USE_MOCKS) return mockHistory;
  return request("/api/history");
}

export async function getReport(sessionId) {
  if (USE_MOCKS) return mockReport;
  return request(`/api/report/${encodeURIComponent(sessionId)}`);
}
