import { NavLink } from "react-router-dom";
import {
  FileText,
  BookOpen,
  Bot,
  Clock,
  Settings,
  Globe,
  ClipboardList,
  ChartNoAxesCombined,
  Radar,
  Code2,
} from "lucide-react";
import type { Lang, Strings } from "../i18n";

interface SidebarProps {
  t: Strings;
  lang: Lang;
  onLangChange: (lang: Lang) => void;
}

const navItems = [
  { to: "/resume", icon: FileText, key: "resume" as const },
  { to: "/interview-prep", icon: BookOpen, key: "interviewPrep" as const },
  { to: "/mock-interview", icon: Bot, key: "mockInterview" as const },
  { to: "/ai-coding", icon: Code2, key: "aiCoding" as const },
  { to: "/history", icon: Clock, key: "history" as const },
  { to: "/job-tracker", icon: ClipboardList, key: "jobTracker" as const },
  { to: "/job-radar", icon: Radar, key: "jobRadar" as const },
  { to: "/ai-monitoring", icon: ChartNoAxesCombined, key: "aiMonitoring" as const },
  { to: "/settings", icon: Settings, key: "settings" as const },
];

export default function Sidebar({ t, lang, onLangChange }: SidebarProps) {
  return (
    <aside className="fixed left-0 top-0 z-40 flex h-screen w-52 flex-col border-r border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-800">
      <div className="flex h-16 items-center gap-3 border-b border-gray-200 px-4 dark:border-gray-700">
        <img src="/logo.png" alt={t.appName} title={t.appName} className="h-9 w-9 flex-shrink-0 rounded-xl object-cover" />
        <div className="min-w-0">
          <div className="truncate text-sm font-bold text-gray-900 dark:text-white">{t.appName}</div>
          <div className="truncate text-[10px] text-gray-500 dark:text-gray-400">AI Career Assistant</div>
        </div>
      </div>
      <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4">
        {navItems.map(({ to, icon: Icon, key }) => (
          <NavLink
            key={to}
            to={to}
            title={t.nav[key]}
            aria-label={t.nav[key]}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${isActive
                ? "bg-brand-50 text-brand-700 dark:bg-brand-900/30 dark:text-brand-300"
                : "text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-700"}`
            }
          >
            <Icon className="h-5 w-5 flex-shrink-0" />
            <span className="truncate">{t.nav[key]}</span>
          </NavLink>
        ))}
      </nav>
      <button
        onClick={() => onLangChange(lang === "zh" ? "en" : "zh")}
        title={lang === "zh" ? "English" : "中文"}
        aria-label={lang === "zh" ? "Switch to English" : "切换到中文"}
        className="m-3 flex items-center gap-3 rounded-lg border-t border-gray-200 px-3 py-2.5 text-sm text-gray-500 hover:bg-gray-100 dark:border-gray-700 dark:text-gray-400 dark:hover:bg-gray-700"
      >
        <Globe className="h-4 w-4" />
        <span>{lang === "zh" ? "English" : "中文"}</span>
      </button>
    </aside>
  );
}
