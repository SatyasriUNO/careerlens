/* Fake responses used when VITE_USE_MOCKS=true (same shapes as the real API). */

export const mockHealth = {
  ollama: true,
  whisper: true,
  shield: "available",
  modules: { resume: "ok", scoring: "ok", interview: "ok" },
};

export const mockResume = {
  resume_id: "r_001",
  role: "SDE",
  parsed: {
    name: "Asha",
    skills: ["Python", "SQL", "React"],
    projects: [{ title: "Library App", bullets: ["Built a REST API for 500 users", "Cut page load time by 40%"] }],
    experience: [],
    education: ["B.E. CSE, 2027"],
  },
  ats_score: 72,
  ats_checks: [
    { name: "Contact details present", passed: true, tip: "" },
    { name: "Standard section headings", passed: true, tip: "" },
    { name: "Bullets start with action verbs", passed: true, tip: "" },
    { name: "Bullets contain numbers", passed: false, tip: "Add measurable results to more bullet points" },
    { name: "GitHub or LinkedIn link", passed: false, tip: "Add your GitHub profile link near your name" },
  ],
  keywords: { matched: ["python", "sql", "react", "rest api"], missing: ["git", "docker", "data structures"] },
  feedback: {
    strengths: ["Clear project section with a measurable result", "Relevant core skills for the role"],
    weaknesses: ["No internship or work experience listed", "Few numbers in bullet points"],
    rewrites: [
      { original: "Worked on a website for college fest", improved: "Built a React website for the college fest used by 1,200 students, cutting registration time by 30%" },
    ],
  },
};

export const mockQuestions = [
  { id: "q1", index: 1, total: 5, type: "intro", text: "Tell me about yourself and why you want this role." },
  { id: "q2", index: 2, total: 5, type: "claim_probe", text: "You wrote that you cut page load time by 40%. How did you measure that?" },
  { id: "q3", index: 3, total: 5, type: "claim_probe", text: "Your REST API served 500 users. How did you design it to handle them?" },
  { id: "q4", index: 4, total: 5, type: "technical", text: "What is the difference between a process and a thread?" },
  { id: "q5", index: 5, total: 5, type: "behavioural", text: "Tell me about a time you disagreed with a teammate. What did you do?" },
];

export function mockAnswer(questionId, inputMode, gaze) {
  const i = mockQuestions.findIndex((q) => q.id === questionId);
  return {
    transcript: "This is a sample transcript of the answer for demo mode.",
    input_mode: inputMode,
    speech: inputMode === "voice" ? { wpm: 138, filler_count: 4, long_pauses: 1, duration_s: 52 } : null,
    gaze: gaze || null,
    evaluation: {
      score: 7,
      clarity: 8,
      strengths: ["Clear structure", "Mentioned a real project"],
      missing_points: ["Say what you personally did, not just the team"],
      better_answer: "I'm a final-year CSE student who builds full-stack apps. In my Library App I profiled slow pages with Lighthouse and cut load time by 40%...",
    },
    next_question: mockQuestions[i + 1] || null,
  };
}

export const mockReport = {
  session_id: "s_001",
  role: "SDE",
  scores: { communication: 74, confidence: 66, technical: 70, resume: 72 },
  score_notes: { communication: "measured", confidence: "measured" },
  answers: mockQuestions.map((q) => ({
    question: q.text,
    type: q.type,
    transcript: "This is a sample transcript of the answer for demo mode.",
    input_mode: "voice",
    speech: { wpm: 138, filler_count: 4, long_pauses: 1, duration_s: 52 },
    gaze: { eye_contact_pct: 71, look_away_count: 3, face_present_pct: 98, tracking_quality: "good", duration_s: 52.4 },
    evaluation: {
      score: 7,
      clarity: 8,
      strengths: ["Clear structure"],
      missing_points: ["Add one number to show impact"],
      better_answer: "A stronger answer would state the situation, your action, and the measurable result.",
    },
  })),
  roadmap: [
    { skill: "Git", why: "Missing keyword for SDE", resources: [{ title: "Pro Git book (free)", url: "https://git-scm.com/book/en/v2" }], days: "1-2" },
    { skill: "Docker", why: "Missing keyword for SDE", resources: [{ title: "Docker getting started", url: "https://docs.docker.com/get-started/" }], days: "3-5" },
  ],
  integrity: { status: "clear", events: [], reason: "" },
};

export const mockHistory = [
  { session_id: "s_001", date: "2026-10-01 18:20", role: "SDE", scores: mockReport.scores },
];

export const mockShield = { status: "clear", findings: [], active: true, reason: "", last_scan: "14:02:11" };
