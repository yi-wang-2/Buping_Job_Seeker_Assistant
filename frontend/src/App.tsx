import { useState, useEffect } from "react";
import { Routes, Route, Navigate, useLocation } from "react-router-dom";
import Sidebar from "./components/Sidebar";
import ResumeGenerate from "./pages/ResumeGenerate";
import InterviewPrep from "./pages/InterviewPrep";
import MockInterview from "./pages/MockInterview";
import History from "./pages/History";
import JobTracker from "./pages/JobTracker";
import SettingsPage from "./pages/Settings";
import AIMonitoring from "./pages/AIMonitoring";
import { getStrings, useLang } from "./i18n";

const SIDEBAR_OPEN_KEY = "buping_sidebar_open";

export default function App() {
  const [lang, setLang] = useLang();
  const t = getStrings(lang);
  const location = useLocation();

  // Sidebar collapse state — persisted in localStorage
  const [sidebarOpen, setSidebarOpen] = useState<boolean>(() => {
    if (typeof window === "undefined") return true;
    const stored = window.localStorage.getItem(SIDEBAR_OPEN_KEY);
    return stored === null ? true : stored === "true";
  });

  useEffect(() => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(SIDEBAR_OPEN_KEY, String(sidebarOpen));
    }
  }, [sidebarOpen]);

  const toggleSidebar = () => setSidebarOpen((prev) => !prev);

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      <Sidebar
        t={t}
        lang={lang}
        onLangChange={setLang}
        isOpen={sidebarOpen}
        onToggle={toggleSidebar}
      />

      {/* Main content — margin adjusts based on sidebar state */}
      <main
        className={`min-h-screen transition-all duration-300 ${sidebarOpen ? "ml-64" : "ml-0"}`}
      >
        <div className="px-8 py-6">
          {/* Header */}
          <div className="mb-6">
            <p className="text-sm text-gray-500 dark:text-gray-400">{t.subtitle}</p>
          </div>

          <Routes location={location}>
            <Route path="/" element={<Navigate to="/resume" replace />} />
            <Route path="/resume" element={<ResumeGenerate t={t} />} />
            <Route path="/interview-prep" element={<InterviewPrep t={t} />} />
            <Route path="/mock-interview" element={<MockInterview t={t} />} />
            <Route path="/history" element={<History t={t} />} />
            <Route path="/job-tracker" element={<JobTracker t={t} />} />
            <Route path="/ai-monitoring" element={<AIMonitoring t={t} />} />
            <Route path="/settings" element={<SettingsPage t={t} />} />
            <Route path="*" element={<Navigate to="/resume" replace />} />
          </Routes>

          {/* Footer */}
          <footer className="mt-12 border-t border-gray-200 pt-6 dark:border-gray-700">
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
          </footer>
        </div>
      </main>
    </div>
  );
}
