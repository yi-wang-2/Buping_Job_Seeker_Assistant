import { NavLink } from "react-router-dom";
import {
  FileText,
  BookOpen,
  Bot,
  Clock,
  Settings,
  Globe,
  PanelLeftClose,
  PanelLeftOpen,
  ClipboardList,
} from "lucide-react";
import type { Lang, Strings } from "../i18n";

interface SidebarProps {
  t: Strings;
  lang: Lang;
  onLangChange: (lang: Lang) => void;
  isOpen: boolean;
  onToggle: () => void;
}

const navItems = [
  { to: "/resume", icon: FileText, key: "resume" as const },
  { to: "/interview-prep", icon: BookOpen, key: "interviewPrep" as const },
  { to: "/mock-interview", icon: Bot, key: "mockInterview" as const },
  { to: "/history", icon: Clock, key: "history" as const },
  { to: "/job-tracker", icon: ClipboardList, key: "jobTracker" as const },
  { to: "/settings", icon: Settings, key: "settings" as const },
];

export default function Sidebar({ t, lang, onLangChange, isOpen, onToggle }: SidebarProps) {
  return (
    <>
      {/* Expanded Sidebar */}
      <aside
        className={`fixed left-0 top-0 z-40 h-screen w-64 border-r border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-800 flex flex-col transition-transform duration-300 ${isOpen ? "translate-x-0" : "-translate-x-full"}`}
      >
        {/* Logo + Toggle button */}
        <div className="flex h-16 items-center gap-3 border-b border-gray-200 px-4 dark:border-gray-700">
          <img
            src="/logo.png"
            alt={t.appName}
            className="h-9 w-9 flex-shrink-0 rounded-xl object-cover"
          />
          <div className="min-w-0 flex-1">
            <h1 className="truncate text-lg font-bold text-gray-900 dark:text-white">{t.appName}</h1>
            <p className="truncate text-[10px] leading-tight text-gray-500 dark:text-gray-400">AI Career Assistant</p>
          </div>
          <button
            onClick={onToggle}
            className="flex-shrink-0 rounded-lg p-1.5 text-gray-500 transition-colors hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-700"
            title={t.sidebar?.toggle ?? "Collapse sidebar"}
            aria-label="Collapse sidebar"
          >
            <PanelLeftClose className="h-4 w-4" />
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 space-y-1 px-3 py-4 overflow-y-auto">
          {navItems.map(({ to, icon: Icon, key }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${isActive ? "bg-brand-50 text-brand-700 dark:bg-brand-900/30 dark:text-brand-300" : "text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-700"}`
              }
            >
              <Icon className="h-5 w-5 flex-shrink-0" />
              {t.nav[key]}
            </NavLink>
          ))}
        </nav>

        {/* Language toggle */}
        <div className="border-t border-gray-200 px-4 py-3 dark:border-gray-700">
          <button
            onClick={() => onLangChange(lang === "zh" ? "en" : "zh")}
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-700 transition-colors"
          >
            <Globe className="h-4 w-4" />
            {lang === "zh" ? "English" : "中文"}
          </button>
        </div>
      </aside>

      {/* Collapsed state — floating expand button */}
      {!isOpen && (
        <button
          onClick={onToggle}
          className="fixed left-4 top-4 z-50 flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm font-medium text-gray-700 shadow-md transition-all hover:bg-gray-50 hover:shadow-lg dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700"
          title={t.sidebar?.expand ?? "Expand sidebar"}
          aria-label="Expand sidebar"
        >
          <PanelLeftOpen className="h-4 w-4" />
          <span className="hidden sm:inline">{t.appName}</span>
        </button>
      )}
    </>
  );
}
