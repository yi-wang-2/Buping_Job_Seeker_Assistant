import { useState, useEffect, useRef, useCallback } from "react";
import { Settings as SettingsIcon, Save, FileEdit, Loader2, Upload, FileText, CheckCircle2, AlertCircle } from "lucide-react";
import type { Strings } from "../i18n";
import {
  getSettings,
  saveSettings,
  getResumeContent,
  saveResumeContent,
  uploadResume,
} from "../api/client";

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

  const [uploadStatus, setUploadStatus] = useState<"idle" | "parsing" | "success" | "error">("idle");
  const [uploadMessage, setUploadMessage] = useState("");
  const [uploadedFilename, setUploadedFilename] = useState("");
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

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
      setUploadStatus("idle");
      setUploadMessage("");
      setUploadedFilename("");
      setTimeout(() => setResumeStatus(""), 3000);
    } catch (err: any) {
      setResumeStatus(`❌ ${err.message}`);
    }
  };

  const handleResumeLangChange = (lang: string) => {
    setResumeLang(lang);
    loadResume(lang);
  };

  const handleFileUpload = useCallback(async (file: File) => {
    setUploadStatus("parsing");
    setUploadMessage(st.uploadStatus);
    setUploadedFilename(file.name);
    try {
      const result = await uploadResume(file, resumeLang, {
        apiKey: apiKey || undefined,
        modelType,
        baseUrl,
      });
      setResumeContent(result.yaml_content);
      setUploadStatus("success");
      setUploadMessage(st.uploadSuccess);
    } catch (err: any) {
      setUploadStatus("error");
      setUploadMessage(err?.response?.data?.detail || st.uploadError);
    }
  }, [apiKey, modelType, baseUrl, resumeLang, st.uploadStatus, st.uploadSuccess, st.uploadError]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFileUpload(file);
  }, [handleFileUpload]);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => setIsDragging(false);

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFileUpload(file);
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

      {/* Upload Resume Document */}
      <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm dark:border-gray-700 dark:bg-gray-800">
        <h3 className="mb-5 flex items-center gap-2 text-lg font-semibold text-gray-900 dark:text-white">
          <Upload className="h-5 w-5 text-brand-500" />
          {st.uploadResume}
        </h3>
        <p className="mb-4 text-sm text-gray-500 dark:text-gray-400">{st.uploadHint}</p>

        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.docx,.html,.htm,.txt,.md,.yaml,.yml,.json,.tex"
          onChange={handleFileInputChange}
          className="hidden"
        />

        <div
          onClick={() => fileInputRef.current?.click()}
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          className={`
            cursor-pointer rounded-lg border-2 border-dashed p-8 text-center transition-colors
            ${isDragging
              ? "border-brand-500 bg-brand-50 dark:bg-brand-900/20"
              : "border-gray-300 bg-gray-50 hover:border-brand-400 hover:bg-brand-50/50 dark:border-gray-600 dark:bg-gray-700/30 dark:hover:border-brand-400"}
          `}
        >
          <FileText className="mx-auto mb-3 h-10 w-10 text-gray-400 dark:text-gray-500" />
          <p className="mb-1 text-sm font-medium text-gray-700 dark:text-gray-200">
            {st.uploadButton}
          </p>
          <p className="text-xs text-gray-400 dark:text-gray-500">{st.uploadDrag}</p>
        </div>

        {/* Upload status */}
        {uploadStatus === "parsing" && (
          <div className="mt-4 flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
            <Loader2 className="h-4 w-4 animate-spin text-brand-500" />
            {uploadMessage}
          </div>
        )}
        {uploadStatus === "success" && (
          <div className="mt-4 flex items-center gap-2 text-sm text-green-600 dark:text-green-400">
            <CheckCircle2 className="h-4 w-4" />
            {uploadMessage}
            {uploadedFilename && (
              <span className="ml-1 font-medium">({uploadedFilename})</span>
            )}
          </div>
        )}
        {uploadStatus === "error" && (
          <div className="mt-4 flex items-center gap-2 text-sm text-red-600 dark:text-red-400">
            <AlertCircle className="h-4 w-4" />
            {uploadMessage}
          </div>
        )}
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
