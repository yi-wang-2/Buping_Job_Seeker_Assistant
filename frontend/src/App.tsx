import { Routes, Route, Navigate, useLocation } from "react-router-dom";
import Sidebar from "./components/Sidebar";
import ResumeGenerate from "./pages/ResumeGenerate";
import InterviewPrep from "./pages/InterviewPrep";
import MockInterview from "./pages/MockInterview";
import History from "./pages/History";
import JobTracker from "./pages/JobTracker";
import JobRadar from "./pages/JobRadar";
import SettingsPage from "./pages/Settings";
import AIMonitoring from "./pages/AIMonitoring";
import AICodingPractice from "./pages/AICodingPractice";
import WorkspaceShell from "./layouts/WorkspaceShell";
import { getStrings, useLang } from "./i18n";

const WORKSPACE_PAGES = new Set(["/resume", "/interview-prep", "/ai-coding", "/job-radar"]);
const IMMERSIVE_PAGES = new Set(["/resume", "/interview-prep", "/mock-interview", "/ai-coding"]);

export default function App() {
  const [lang, setLang] = useLang();
  const t = getStrings(lang);
  const location = useLocation();
  const isWorkspace = WORKSPACE_PAGES.has(location.pathname);
  const isImmersive = IMMERSIVE_PAGES.has(location.pathname);

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      <Sidebar t={t} lang={lang} onLangChange={setLang} />

      {/* The navigation rail occupies the same width on every route. */}
      <main className={`ml-52 ${isImmersive ? "h-screen overflow-hidden" : "min-h-screen"}`}>
        <div className={isImmersive ? "h-full overflow-hidden px-3 py-3 lg:px-4" : isWorkspace ? "px-3 py-3 lg:px-4" : "px-8 py-6"}>
          {!isImmersive && <div className={isWorkspace ? "mb-3" : "mb-6"}>
            <p className="text-sm text-gray-500 dark:text-gray-400">{t.subtitle}</p>
          </div>}

          <Routes location={location}>
            <Route path="/" element={<Navigate to="/resume" replace />} />
            <Route path="/resume" element={<WorkspaceShell page="resume" lang={lang}><ResumeGenerate t={t} /></WorkspaceShell>} />
            <Route path="/interview-prep" element={<WorkspaceShell page="interview-prep" lang={lang}><InterviewPrep t={t} /></WorkspaceShell>} />
            <Route path="/mock-interview" element={<MockInterview t={t} />} />
            <Route path="/ai-coding" element={<WorkspaceShell page="ai-coding" lang={lang}><AICodingPractice t={t} /></WorkspaceShell>} />
            <Route path="/history" element={<History t={t} />} />
            <Route path="/job-tracker" element={<JobTracker t={t} />} />
            <Route path="/job-radar" element={<WorkspaceShell page="job-radar" lang={lang}><JobRadar t={t} /></WorkspaceShell>} />
            <Route path="/ai-monitoring" element={<AIMonitoring t={t} />} />
            <Route path="/settings" element={<SettingsPage t={t} />} />
            <Route path="*" element={<Navigate to="/resume" replace />} />
          </Routes>

          {!isImmersive && <footer className="mt-12 border-t border-gray-200 pt-6 dark:border-gray-700">
            <p className="text-center text-xs text-gray-400 dark:text-gray-500">{t.footer}</p>
            <p className="mt-2 text-center text-xs">
              <a
                href="https://github.com/yi-wang-2/Buping_Job_Seeker_Assistant"
                target="_blank"
                rel="noreferrer"
                className="text-brand-600 hover:underline dark:text-brand-400"
              >
                GitHub · Buping Job Seeker Assistant
              </a>
            </p>
          </footer>}
        </div>
      </main>
    </div>
  );
}
