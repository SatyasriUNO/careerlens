import { NavLink, Route, Routes } from "react-router-dom";
import Upload from "./pages/Upload";
import ResumeReport from "./pages/ResumeReport";
import InterviewRoom from "./pages/InterviewRoom";
import FinalReport from "./pages/FinalReport";
import History from "./pages/History";
import GazeDebug from "./gaze/GazeDebug";
import { USE_MOCKS } from "./api";

export default function App() {
  return (
    <div className="app">
      <header className="topbar">
        <NavLink to="/" className="brand">
          <span className="brand-mark" aria-hidden="true">◎</span>
          CareerLens
        </NavLink>
        <nav className="nav">
          <NavLink to="/" end>New practice</NavLink>
          <NavLink to="/history">History</NavLink>
        </nav>
        <span className="offline-badge" title="Everything runs on this laptop">
          {USE_MOCKS ? "Demo data" : "On-device"}
        </span>
      </header>

      <main className="page">
        <Routes>
          <Route path="/" element={<Upload />} />
          <Route path="/resume" element={<ResumeReport />} />
          <Route path="/interview" element={<InterviewRoom />} />
          <Route path="/report" element={<FinalReport />} />
          <Route path="/report/:sessionId" element={<FinalReport />} />
          <Route path="/history" element={<History />} />
          <Route path="/gaze-debug" element={<GazeDebug />} />
          <Route path="*" element={<p className="muted">Page not found.</p>} />
        </Routes>
      </main>
    </div>
  );
}
