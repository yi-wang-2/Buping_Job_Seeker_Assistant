import { Routes, Route, Navigate, useLocation } from "react-router-dom";
import Sidebar from "./components/Sidebar";
import ResumeGenerate from "./pages/ResumeGenerate";
import InterviewPrep from "./pages/InterviewPrep";
import MockInterview from "./pages/MockInterview";
import History from "./pages/History";
import SettingsPage from "./pages/Settings";
import { getStrings, useLang } from "./i18n";

export default function App() {
  const [lang, setLang] = useLang();
  const t = getStrings(lang);
  const location = useLocation();

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      <Sidebar t={t} lang={lang} onLangChange={setLang} />

      {/* Main content */}
      <main className="ml-64 min-h-screen">
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
            <Route path="/settings" element={<SettingsPage t={t} />} />
            <Route path="*" element={<Navigate to="/resume" replace />} />
          </Routes>

          {/* Footer */}
          <footer className="mt-12 border-t border-gray-200 pt-6 dark:border-gray-700">
            <p className="text-center text-xs text-gray-400 dark:text-gray-500">{t.footer}</p>
          </footer>
        </div>
      </main>
    </div>
  );
}
