import { useState, useEffect } from "react";
import { Download, Sparkles, Palette } from "lucide-react";
import type { Strings } from "../i18n";
import { getStyles, generateResume, getDownloadUrl } from "../api/client";
import LoadingSpinner from "../components/LoadingSpinner";

export default function ResumeGenerate({ t }: { t: Strings }) {
  const rt = t.resume;
  const [styles, setStyles] = useState<Record<string, { file: string; author: string }>>({});
  const [apiKey, setApiKey] = useState("");
  const [modelType, setModelType] = useState("anthropic");
  const [baseUrl, setBaseUrl] = useState("https://api.minimaxi.com/anthropic");
  const [styleName, setStyleName] = useState("");
  const [jobDesc, setJobDesc] = useState("");
  const [resumeLang, setResumeLang] = useState("zh");
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState("");
  const [downloadFile, setDownloadFile] = useState("");

  useEffect(() => {
    getStyles().then((s) => {
      setStyles(s);
      const keys = Object.keys(s);
      if (keys.length > 0 && !styleName) setStyleName(keys[0]);
    }).catch(() => {});
    // Load saved config
    import("../api/client").then(({ getSettings }) => {
      getSettings().then((cfg) => {
        if (cfg.llm_api_key) setApiKey(cfg.llm_api_key);
        if (cfg.llm_model_type) setModelType(cfg.llm_model_type);
        if (cfg.llm_base_url) setBaseUrl(cfg.llm_base_url);
        if (cfg.resume_language) setResumeLang(cfg.resume_language);
      }).catch(() => {});
    });
  }, []);

  const handleGenerate = async () => {
    setLoading(true);
    setStatus(rt.generating);
    setDownloadFile("");
    try {
      const result = await generateResume({
        api_key: apiKey,
        model_type: modelType,
        base_url: baseUrl,
        style_name: styleName,
        job_description: jobDesc || undefined,
        resume_language: resumeLang,
      });
      setStatus(`${rt.success} ${result.filename}`);
      setDownloadFile(result.filename);
    } catch (err: any) {
      setStatus(`${rt.error}: ${err.response?.data?.detail || err.message}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page-enter max-w-5xl mx-auto">
      <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-6">{rt.title}</h2>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Config Panel */}
        <div className="lg:col-span-1 space-y-4">
          <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-700 dark:bg-gray-800">
            <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold text-gray-700 dark:text-gray-300">
              <Sparkles className="h-4 w-4 text-brand-500" />
              {rt.config}
            </h3>

            <div className="space-y-3">
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">{rt.apiKey}</label>
                <input
                  type="password"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder={rt.apiKeyPlaceholder}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500 dark:border-gray-600 dark:bg-gray-700 dark:text-white"
                />
              </div>

              <div>
                <label className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">{rt.modelType}</label>
                <select
                  value={modelType}
                  onChange={(e) => setModelType(e.target.value)}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none dark:border-gray-600 dark:bg-gray-700 dark:text-white"
                >
                  <option value="anthropic">Anthropic</option>
                  <option value="openai">OpenAI</option>
                </select>
              </div>

              <div>
                <label className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">{rt.baseUrl}</label>
                <input
                  type="text"
                  value={baseUrl}
                  onChange={(e) => setBaseUrl(e.target.value)}
                  placeholder={rt.baseUrlPlaceholder}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500 dark:border-gray-600 dark:bg-gray-700 dark:text-white"
                />
              </div>

              <div>
                <label className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">{rt.resumeLang}</label>
                <select
                  value={resumeLang}
                  onChange={(e) => setResumeLang(e.target.value)}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none dark:border-gray-600 dark:bg-gray-700 dark:text-white"
                >
                  <option value="zh">中文</option>
                  <option value="en">English</option>
                </select>
              </div>
            </div>
          </div>

          {/* Style Selection */}
          <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-700 dark:bg-gray-800">
            <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold text-gray-700 dark:text-gray-300">
              <Palette className="h-4 w-4 text-brand-500" />
              {rt.style}
            </h3>
            <div className="space-y-2">
              {Object.entries(styles).map(([name, info]) => (
                <label
                  key={name}
                  className={`flex cursor-pointer items-center gap-3 rounded-lg border p-3 transition-colors ${
                    styleName === name
                      ? "border-brand-500 bg-brand-50 dark:bg-brand-900/20"
                      : "border-gray-200 hover:border-gray-300 dark:border-gray-600"
                  }`}
                >
                  <input
                    type="radio"
                    name="style"
                    value={name}
                    checked={styleName === name}
                    onChange={() => setStyleName(name)}
                    className="text-brand-600 focus:ring-brand-500"
                  />
                  <div>
                    <div className="text-sm font-medium text-gray-900 dark:text-white">{name}</div>
                    <div className="text-xs text-gray-500 dark:text-gray-400">by {info.author}</div>
                  </div>
                </label>
              ))}
              {Object.keys(styles).length === 0 && (
                <p className="text-sm text-gray-500 dark:text-gray-400">Loading styles...</p>
              )}
            </div>
          </div>
        </div>

        {/* Main Panel */}
        <div className="lg:col-span-2 space-y-4">
          <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-700 dark:bg-gray-800">
            <label className="mb-2 block text-sm font-semibold text-gray-700 dark:text-gray-300">{rt.jobDesc}</label>
            <textarea
              value={jobDesc}
              onChange={(e) => setJobDesc(e.target.value)}
              placeholder={rt.jobDescPlaceholder}
              rows={10}
              className="w-full rounded-lg border border-gray-300 px-4 py-3 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500 dark:border-gray-600 dark:bg-gray-700 dark:text-white resize-none"
            />
          </div>

          <button
            onClick={handleGenerate}
            disabled={loading}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-brand-600 to-brand-700 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-brand-500/25 transition-all hover:from-brand-700 hover:to-brand-800 hover:shadow-xl disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? <LoadingSpinner size="sm" /> : <Sparkles className="h-4 w-4" />}
            {loading ? rt.generating : rt.generate}
          </button>

          {/* Status */}
          {status && (
            <div className={`rounded-xl border p-4 text-sm ${
              status.includes("成功") || status.includes("success")
                ? "border-green-200 bg-green-50 text-green-800 dark:border-green-800 dark:bg-green-900/20 dark:text-green-300"
                : status.includes("失败") || status.includes("error") || status.includes("Error")
                ? "border-red-200 bg-red-50 text-red-800 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300"
                : "border-blue-200 bg-blue-50 text-blue-800 dark:border-blue-800 dark:bg-blue-900/20 dark:text-blue-300"
            }`}>
              {status}
            </div>
          )}

          {/* Download */}
          {downloadFile && (
            <a
              href={getDownloadUrl(downloadFile)}
              download
              className="flex items-center gap-2 rounded-xl border border-brand-200 bg-brand-50 px-5 py-3 text-sm font-medium text-brand-700 transition-colors hover:bg-brand-100 dark:border-brand-800 dark:bg-brand-900/20 dark:text-brand-300"
            >
              <Download className="h-4 w-4" />
              {rt.download}: {downloadFile}
            </a>
          )}
        </div>
      </div>
    </div>
  );
}
