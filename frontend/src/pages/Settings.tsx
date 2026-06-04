import { useState, useEffect } from "react";
import { Settings as SettingsIcon, Save, FileEdit, Loader2 } from "lucide-react";
import type { Strings } from "../i18n";
import { getSettings, saveSettings, getResumeContent, saveResumeContent } from "../api/client";

export default function SettingsPage({ t }: { t: Strings }) {
  const st = t.settings;

  const [apiKey, setApiKey] = useState("");
  const [modelType, setModelType] = useState("anthropic");
  const [baseUrl, setBaseUrl] = useState("https://api.minimaxi.com/anthropic");
  const [resumeLang, setResumeLang] = useState("zh");
  const [configStatus, setConfigStatus] = useState("");

  const [resumeContent, setResumeContent] = useState("");
  const [resumeStatus, setResumeStatus] = useState("");
  const [loadingResume, setLoadingResume] = useState(false);

  useEffect(() => {
    getSettings().then((cfg) => {
      setApiKey(cfg.llm_api_key);
      setModelType(cfg.llm_model_type);
      setBaseUrl(cfg.llm_base_url);
      setResumeLang(cfg.resume_language);
      loadResume(cfg.resume_language);
    }).catch(() => {});
  }, []);

  const loadResume = async (lang: string) => {
    setLoadingResume(true);
    try {
      const result = await getResumeContent(lang);
      setResumeContent(result.content);
    } catch {
      setResumeContent("# Failed to load resume content");
    } finally {
      setLoadingResume(false);
    }
  };

  const handleSaveConfig = async () => {
    try {
      await saveSettings({
        llm_api_key: apiKey,
        llm_model_type: modelType,
        llm_base_url: baseUrl,
        resume_language: resumeLang,
      });
      setConfigStatus(st.saved);
      setTimeout(() => setConfigStatus(""), 3000);
    } catch (err: any) {
      setConfigStatus(`❌ ${err.message}`);
    }
  };

  const handleSaveResume = async () => {
    try {
      await saveResumeContent({ content: resumeContent, language: resumeLang });
      setResumeStatus(st.resumeSaved);
      setTimeout(() => setResumeStatus(""), 3000);
    } catch (err: any) {
      setResumeStatus(`❌ ${err.message}`);
    }
  };

  const handleResumeLangChange = (lang: string) => {
    setResumeLang(lang);
    loadResume(lang);
  };

  return (
    <div className="page-enter max-w-4xl mx-auto space-y-6">
      <h2 className="text-2xl font-bold text-gray-900 dark:text-white">{st.title}</h2>

      {/* LLM Config */}
      <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm dark:border-gray-700 dark:bg-gray-800">
        <h3 className="mb-5 flex items-center gap-2 text-lg font-semibold text-gray-900 dark:text-white">
          <SettingsIcon className="h-5 w-5 text-brand-500" />
          {st.config}
        </h3>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">{st.apiKey}</label>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500 dark:border-gray-600 dark:bg-gray-700 dark:text-white"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">{st.modelType}</label>
            <select
              value={modelType}
              onChange={(e) => setModelType(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-brand-500 focus:outline-none dark:border-gray-600 dark:bg-gray-700 dark:text-white"
            >
              <option value="anthropic">Anthropic</option>
              <option value="openai">OpenAI</option>
            </select>
          </div>
          <div>
            <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">{st.baseUrl}</label>
            <input
              type="text"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500 dark:border-gray-600 dark:bg-gray-700 dark:text-white"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">{st.resumeLang}</label>
            <select
              value={resumeLang}
              onChange={(e) => handleResumeLangChange(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-brand-500 focus:outline-none dark:border-gray-600 dark:bg-gray-700 dark:text-white"
            >
              <option value="zh">中文</option>
              <option value="en">English</option>
            </select>
          </div>
        </div>

        <div className="mt-5 flex items-center gap-3">
          <button
            onClick={handleSaveConfig}
            className="flex items-center gap-2 rounded-lg bg-brand-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-brand-700 transition-colors"
          >
            <Save className="h-4 w-4" />
            {st.save}
          </button>
          {configStatus && (
            <span className={`text-sm ${configStatus.startsWith("❌") ? "text-red-600" : "text-green-600"}`}>
              {configStatus}
            </span>
          )}
        </div>
      </div>

      {/* Resume Editor */}
      <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm dark:border-gray-700 dark:bg-gray-800">
        <h3 className="mb-5 flex items-center gap-2 text-lg font-semibold text-gray-900 dark:text-white">
          <FileEdit className="h-5 w-5 text-brand-500" />
          {st.resumeEditor}
        </h3>

        {loadingResume ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-6 w-6 animate-spin text-brand-500" />
          </div>
        ) : (
          <textarea
            value={resumeContent}
            onChange={(e) => setResumeContent(e.target.value)}
            rows={20}
            className="w-full rounded-lg border border-gray-300 px-4 py-3 font-mono text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500 dark:border-gray-600 dark:bg-gray-700 dark:text-white resize-y"
          />
        )}

        <div className="mt-4 flex items-center gap-3">
          <button
            onClick={handleSaveResume}
            className="flex items-center gap-2 rounded-lg bg-brand-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-brand-700 transition-colors"
          >
            <Save className="h-4 w-4" />
            {st.saveResume}
          </button>
          {resumeStatus && (
            <span className={`text-sm ${resumeStatus.startsWith("❌") ? "text-red-600" : "text-green-600"}`}>
              {resumeStatus}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
