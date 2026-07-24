import { useState, useEffect, useRef, useCallback } from "react";
import { Settings as SettingsIcon, Save, FileEdit, Loader2, Upload, FileText, CheckCircle2, AlertCircle, Brain, Trash2 } from "lucide-react";
import type { Strings } from "../i18n";
import {
  getSettings,
  saveSettings,
  getResumeContent,
  saveResumeContent,
  uploadResume,
  clearAIMemory,
  getMemorySettings,
  saveMemorySettings,
  type ResumeValidation,
} from "../api/client";
import { useAvailableModels } from "../hooks/useAvailableModels";

// Preset list of supported LLM providers. Choosing one auto-fills the
// base_url AND protocol fields. Protocol is decoupled from provider so
// providers like MiniMax that expose multiple APIs can be selected by
// protocol variant.
type LlmProtocol = "anthropic" | "openai_chat" | "openai_response";

interface ModelPreset {
  id: string;
  label: string;
  defaultBaseUrl: string;
  protocol: LlmProtocol;
}

const MODEL_PRESETS: ReadonlyArray<ModelPreset> = [
  // --- Native Anthropic protocol ---
  { id: "anthropic",     label: "Anthropic (Claude 官方)",          defaultBaseUrl: "https://api.anthropic.com",        protocol: "anthropic" },
  { id: "minimax-anth",  label: "MiniMax (Anthropic 协议)",        defaultBaseUrl: "https://api.minimaxi.com/anthropic", protocol: "anthropic" },

  // --- OpenAI Chat Completions protocol (most common) ---
  { id: "openai",        label: "OpenAI (Chat Completions)",       defaultBaseUrl: "https://api.openai.com/v1",           protocol: "openai_chat" },
  { id: "deepseek",      label: "DeepSeek",                        defaultBaseUrl: "https://api.deepseek.com/v1",        protocol: "openai_chat" },
  { id: "zhipu",         label: "智谱 AI (GLM-4)",                  defaultBaseUrl: "https://open.bigmodel.cn/api/paas/v4", protocol: "openai_chat" },
  { id: "moonshot",      label: "月之暗面 (Kimi)",                  defaultBaseUrl: "https://api.moonshot.cn/v1",         protocol: "openai_chat" },
  { id: "qwen",          label: "通义千问 (Qwen)",                  defaultBaseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1", protocol: "openai_chat" },
  { id: "doubao",        label: "豆包 (Doubao)",                    defaultBaseUrl: "https://ark.cn-beijing.volces.com/api/v3", protocol: "openai_chat" },
  { id: "yi",            label: "零一万物 (Yi)",                    defaultBaseUrl: "https://api.lingyiwanwu.com/v1",    protocol: "openai_chat" },
  { id: "minimax-chat",  label: "MiniMax (OpenAI Chat 协议)",      defaultBaseUrl: "https://api.minimaxi.com/v1",        protocol: "openai_chat" },
  { id: "ollama",        label: "Ollama (本地)",                    defaultBaseUrl: "http://localhost:11434/v1",        protocol: "openai_chat" },

  // --- OpenAI Responses API ---
  { id: "openai-resp",   label: "OpenAI (Responses API)",          defaultBaseUrl: "https://api.openai.com/v1",           protocol: "openai_response" },
  { id: "minimax-resp",  label: "MiniMax (Responses API)",         defaultBaseUrl: "https://api.minimaxi.com/v1",        protocol: "openai_response" },
];

// Lookup a preset by id
const PRESET_BY_ID: Record<string, ModelPreset> = Object.fromEntries(
  MODEL_PRESETS.map((p) => [p.id, p])
);

const DEFAULT_MODEL_BY_PROVIDER: Record<string, string> = {
  anthropic: "claude-sonnet-4-20250514",
  "minimax-anth": "MiniMax-M3",
  openai: "gpt-4o-mini",
  deepseek: "deepseek-chat",
  zhipu: "glm-4-flash",
  moonshot: "moonshot-v1-8k",
  qwen: "qwen-plus",
  yi: "yi-lightning",
  "minimax-chat": "MiniMax-M3",
  "openai-resp": "gpt-4o-mini",
  "minimax-resp": "MiniMax-M3",
};

type UploadParseDiagnostics = {
  llm_attempted?: boolean;
  llm_call_success?: boolean;
  llm_yaml_parse_success?: boolean;
  used_fallback?: boolean;
  fallback_reason?: string;
  extracted_text_chars?: number;
  llm_raw_chars?: number;
  llm_yaml_candidate_chars?: number;
  llm_yaml_error?: string;
};

function formatUploadDiagnostics(d?: UploadParseDiagnostics): string[] {
  if (!d) return [];
  const llmStatus = !d.llm_attempted
    ? "LLM: 未调用"
    : d.llm_call_success
      ? "LLM: 调用成功"
      : "LLM: 调用失败";
  const yamlStatus = d.llm_attempted
    ? d.llm_yaml_parse_success
      ? "YAML解析: 成功"
      : "YAML解析: 失败"
    : "YAML解析: 未执行";
  const fallbackStatus = d.used_fallback
    ? `结果来源: fallback规则${d.fallback_reason ? ` (${d.fallback_reason})` : ""}`
    : "结果来源: LLM结构化结果";
  const sizes = `文本: ${d.extracted_text_chars ?? 0} chars, LLM输出: ${d.llm_raw_chars ?? 0} chars`;
  return [llmStatus, yamlStatus, fallbackStatus, sizes];
}

export default function SettingsPage({ t }: { t: Strings }) {
  const st = t.settings;

  const [apiKey, setApiKey] = useState("");
  const [modelType, setModelType] = useState("anthropic");
  const [modelName, setModelName] = useState("MiniMax-M3");
  const [baseUrl, setBaseUrl] = useState("https://api.minimaxi.com/anthropic");
  const [llmProtocol, setLlmProtocol] = useState<LlmProtocol>("anthropic");
  const availableModels = useAvailableModels(apiKey, baseUrl, llmProtocol);
  const [resumeLang, setResumeLang] = useState("zh");
  const [configStatus, setConfigStatus] = useState("");
  const [memoryEnabled, setMemoryEnabled] = useState(true);
  const [cacheEnabled, setCacheEnabled] = useState(true);
  const [memoryStatus, setMemoryStatus] = useState("");

  const [resumeContent, setResumeContent] = useState("");
  const [resumeStatus, setResumeStatus] = useState("");
  const [loadingResume, setLoadingResume] = useState(false);

  const [uploadStatus, setUploadStatus] = useState<"idle" | "parsing" | "success" | "error">("idle");
  const [uploadMessage, setUploadMessage] = useState("");
  const [uploadDiagnostics, setUploadDiagnostics] = useState<string[]>([]);
  const [uploadedFilename, setUploadedFilename] = useState("");
  const [resumeValidation, setResumeValidation] = useState<ResumeValidation | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    getSettings().then((cfg) => {
      setApiKey(cfg.llm_api_key);
      setModelType(cfg.llm_model_type);
      setModelName(cfg.llm_model || DEFAULT_MODEL_BY_PROVIDER[cfg.llm_model_type] || "");
      setBaseUrl(cfg.llm_base_url);
      setLlmProtocol((cfg.llm_protocol as LlmProtocol) || "anthropic");
      setResumeLang(cfg.resume_language);
      loadResume(cfg.resume_language);
    }).catch(() => {});
    getMemorySettings().then((settings) => {
      setMemoryEnabled(settings.memory_enabled);
      setCacheEnabled(settings.cache_enabled);
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
        llm_model: modelName.trim(),
        llm_base_url: baseUrl,
        llm_protocol: llmProtocol,
        resume_language: resumeLang,
      });
      setConfigStatus(st.saved);
      setTimeout(() => setConfigStatus(""), 3000);
    } catch (err: any) {
      setConfigStatus(`❌ ${err.message}`);
    }
  };

  const handleSaveMemorySettings = async () => {
    try {
      await saveMemorySettings({ memory_enabled: memoryEnabled, cache_enabled: cacheEnabled });
      setMemoryStatus("隐私设置已保存");
    } catch (err: any) {
      setMemoryStatus(`❌ ${err.message}`);
    }
  };

  const handleClearMemory = async () => {
    if (!window.confirm("确定清空全部 AI 长期记忆吗？此操作不可撤销。")) return;
    try {
      const result = await clearAIMemory();
      setMemoryStatus(`已删除 ${result.deleted} 条长期记忆`);
    } catch (err: any) {
      setMemoryStatus(`❌ ${err.message}`);
    }
  };

  const handleSaveResume = async () => {
    try {
      const result = await saveResumeContent({ content: resumeContent, language: resumeLang });
      setResumeValidation(result.validation || null);
      setResumeStatus(st.resumeSaved);
      setUploadStatus("idle");
      setUploadMessage("");
      setUploadDiagnostics([]);
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
    setUploadDiagnostics([]);
    setUploadedFilename(file.name);
    try {
      const result = await uploadResume(file, resumeLang, {
        apiKey: apiKey || undefined,
        modelType,
        modelName,
        baseUrl,
        llmProtocol,
      });
      setResumeContent(result.yaml_content);
      setResumeValidation(result.validation || null);
      setUploadStatus("success");
      setUploadMessage(st.uploadSuccess);
      setUploadDiagnostics(formatUploadDiagnostics(result.parse_diagnostics));
    } catch (err: any) {
      setUploadStatus("error");
      setUploadMessage(err?.response?.data?.detail || st.uploadError);
      setUploadDiagnostics([]);
      setResumeValidation(null);
    }
  }, [apiKey, modelType, modelName, baseUrl, llmProtocol, resumeLang, st.uploadStatus, st.uploadSuccess, st.uploadError]);

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
              onChange={(e) => {
                const newType = e.target.value;
                setModelType(newType);
                // Auto-fill base_url AND protocol when picking a preset.
                const preset = PRESET_BY_ID[newType];
                if (preset) {
                  setBaseUrl(preset.defaultBaseUrl);
                  setLlmProtocol(preset.protocol);
                  setModelName(DEFAULT_MODEL_BY_PROVIDER[newType] || "");
                }
              }}
              className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-brand-500 focus:outline-none dark:border-gray-600 dark:bg-gray-700 dark:text-white"
            >
              {MODEL_PRESETS.map((preset) => (
                <option key={preset.id} value={preset.id}>
                  {preset.label}
                </option>
              ))}
            </select>
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              {st.modelTypeHint}
            </p>
          </div>
          <div>
            <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">模型名称 / Model ID</label>
            {availableModels.length > 0 && (
              <select
                value={availableModels.includes(modelName) ? modelName : ""}
                onChange={(e) => e.target.value && setModelName(e.target.value)}
                className="mb-2 w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-brand-500 focus:outline-none dark:border-gray-600 dark:bg-gray-700 dark:text-white"
              >
                <option value="">选择供应商模型…</option>
                {availableModels.map((model) => <option key={model} value={model}>{model}</option>)}
              </select>
            )}
            <input
              type="text"
              value={modelName}
              onChange={(e) => setModelName(e.target.value)}
              placeholder="deepseek-chat"
              className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500 dark:border-gray-600 dark:bg-gray-700 dark:text-white"
            />
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">切换供应商时会填入推荐值，也可输入该供应商支持的任意模型 ID。</p>
          </div>
          <div>
            <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">
              {st.modelProtocol}
            </label>
            <select
              value={llmProtocol}
              onChange={(e) => setLlmProtocol(e.target.value as LlmProtocol)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-brand-500 focus:outline-none dark:border-gray-600 dark:bg-gray-700 dark:text-white"
            >
              <option value="anthropic">{st.protocolAnthropic}</option>
              <option value="openai_chat">{st.protocolOpenaiChat}</option>
              <option value="openai_response">{st.protocolOpenaiResponse}</option>
            </select>
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              {st.modelProtocolHint}
            </p>
            {llmProtocol === "openai_response" && (
              <p className="mt-2 rounded-md bg-amber-50 px-2 py-1.5 text-xs text-amber-700 dark:bg-amber-900/20 dark:text-amber-300">
                Responses API 需要供应商及当前客户端版本同时支持；系统会严格按此选择发送，不会自动切换协议。若调用失败，请根据真实错误调整配置。
              </p>
            )}
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

      {/* AI memory and cache privacy controls */}
      <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm dark:border-gray-700 dark:bg-gray-800">
        <h3 className="mb-4 flex items-center gap-2 text-lg font-semibold text-gray-900 dark:text-white">
          <Brain className="h-5 w-5 text-brand-500" />
          AI 记忆与隐私
        </h3>
        <div className="space-y-3 text-sm text-gray-700 dark:text-gray-300">
          <label className="flex items-center justify-between gap-4">
            <span>保存求职偏好、简历风格和历史上下文</span>
            <input type="checkbox" checked={memoryEnabled} onChange={(event) => setMemoryEnabled(event.target.checked)} className="h-4 w-4 accent-brand-600" />
          </label>
          <label className="flex items-center justify-between gap-4">
            <span>启用本地 Prompt 响应缓存</span>
            <input type="checkbox" checked={cacheEnabled} onChange={(event) => setCacheEnabled(event.target.checked)} className="h-4 w-4 accent-brand-600" />
          </label>
        </div>
        <div className="mt-5 flex flex-wrap items-center gap-3">
          <button onClick={handleSaveMemorySettings} className="flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700">
            <Save className="h-4 w-4" />保存隐私设置
          </button>
          <button onClick={handleClearMemory} className="flex items-center gap-2 rounded-lg border border-red-300 px-4 py-2 text-sm font-semibold text-red-600 hover:bg-red-50 dark:border-red-800 dark:hover:bg-red-900/20">
            <Trash2 className="h-4 w-4" />清空长期记忆
          </button>
          {memoryStatus && <span className={`text-sm ${memoryStatus.startsWith("❌") ? "text-red-600" : "text-green-600"}`}>{memoryStatus}</span>}
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
          <div className="mt-4 rounded-lg border border-green-200 bg-green-50 p-3 text-sm text-green-700 dark:border-green-800 dark:bg-green-900/20 dark:text-green-300">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4" />
              <span>{uploadMessage}</span>
              {uploadedFilename && (
                <span className="font-medium">({uploadedFilename})</span>
              )}
            </div>
            {uploadDiagnostics.length > 0 && (
              <div className="mt-2 grid gap-1 pl-6 text-xs text-green-700/90 dark:text-green-300/90">
                {uploadDiagnostics.map((item) => (
                  <div key={item}>{item}</div>
                ))}
              </div>
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

      {resumeValidation && (resumeValidation.errors.length > 0 || resumeValidation.warnings.length > 0) && (
        <div className={`rounded-xl border p-4 ${resumeValidation.valid ? "border-amber-300 bg-amber-50 dark:border-amber-800 dark:bg-amber-900/20" : "border-red-300 bg-red-50 dark:border-red-800 dark:bg-red-900/20"}`}>
          <div className={`mb-2 flex items-center gap-2 font-semibold ${resumeValidation.valid ? "text-amber-800 dark:text-amber-300" : "text-red-800 dark:text-red-300"}`}>
            <AlertCircle className="h-5 w-5" />
            {resumeValidation.valid ? "简历信息有待完善" : "缺少关键字段，暂时不能生成简历"}
          </div>
          <div className="space-y-1 text-sm text-gray-700 dark:text-gray-200">
            {resumeValidation.errors.length > 0 && (
              <div className="mb-3">
                <div className="mb-1 font-semibold text-red-800 dark:text-red-300">必须补齐（否则不能生成）</div>
                {resumeValidation.errors.map((item) => (
                  <div key={`error-${item.path}`}><span className="font-mono text-red-700 dark:text-red-300">{item.path}</span>：{item.message}</div>
                ))}
              </div>
            )}
            {resumeValidation.warnings.length > 0 && (
              <div>
                <div className="mb-1 font-semibold text-amber-800 dark:text-amber-300">完善建议（不影响生成）</div>
                {resumeValidation.warnings.map((item) => (
                  <div key={`warning-${item.path}`}><span className="font-mono text-amber-700 dark:text-amber-300">{item.path}</span>：{item.message}</div>
                ))}
              </div>
            )}
          </div>
          {!resumeValidation.valid && (
            <p className="mt-3 text-sm font-medium text-red-700 dark:text-red-300">可以先保存草稿，但必须补齐以上红色关键字段后才能生成。</p>
          )}
        </div>
      )}

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
