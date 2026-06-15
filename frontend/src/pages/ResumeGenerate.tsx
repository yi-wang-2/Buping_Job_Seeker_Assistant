import { useState, useEffect, useRef } from "react";
import { Download, Sparkles, Palette, Eye, ExternalLink, RefreshCw, FileText, Edit3, Save, RotateCcw, Check, History as HistoryIcon, Sparkle } from "lucide-react";
import type { Strings } from "../i18n";
import { getStyles, generateResume, getDownloadUrl, previewResume, getPreviewPageUrl, getHistory, previewSavedResume } from "../api/client";
import LoadingSpinner from "../components/LoadingSpinner";
import { EditableResumePreview } from "../components/editor";

interface HistoryFile {
  name: string;
  path: string;
  size: number;
  modified: string;
}

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
  const [downloadHtmlFile, setDownloadHtmlFile] = useState<string>(""); // e.g. "resume_20250615_103045.html"
  // Generation progress state (0-100, -1 = idle, stage label)
  const [genProgress, setGenProgress] = useState<number>(-1);
  const [genStage, setGenStage] = useState<string>("");

  // Preview state
  const [previewing, setPreviewing] = useState(false);
  const [previewHtml, setPreviewHtml] = useState<string>("");
  const [previewKey, setPreviewKey] = useState<number>(0);
  const previewRef = useRef<HTMLIFrameElement | null>(null);

  // History picker
  const [historyFiles, setHistoryFiles] = useState<HistoryFile[]>([]);
  const [historyOpen, setHistoryOpen] = useState<boolean>(false);
  const [loadingHistory, setLoadingHistory] = useState<boolean>(false);
  const [loadingPreviewFile, setLoadingPreviewFile] = useState<string>(""); // currently loading filename

  // Edit mode state
  const [editMode, setEditMode] = useState<boolean>(false);
  const [editedHtml, setEditedHtml] = useState<string>("");
  const [savedOk, setSavedOk] = useState<boolean>(false);

  useEffect(() => {
    getStyles().then((s) => {
      setStyles(s);
      const keys = Object.keys(s);
      if (keys.length > 0 && !styleName) setStyleName(keys[0]);
    }).catch(() => {});
    import("../api/client").then(({ getSettings }) => {
      getSettings().then((cfg) => {
        if (cfg.llm_api_key) setApiKey(cfg.llm_api_key);
        if (cfg.llm_model_type) setModelType(cfg.llm_model_type);
        if (cfg.llm_base_url) setBaseUrl(cfg.llm_base_url);
        if (cfg.resume_language) setResumeLang(cfg.resume_language);
      }).catch(() => {});
    });
  }, []);

  useEffect(() => {
    if (styleName && resumeLang) {
      handlePreview();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [styleName, resumeLang]);

  const handleGenerate = async () => {
    if (loading) return; // Prevent double click
    setLoading(true);
    setDownloadFile("");
    setGenProgress(0);
    setGenStage(resumeLang === "zh" ? "初始化..." : "Initializing...");
    setStatus(rt.generating);

    // Simulate progress stages while waiting for backend
    // (Backend is synchronous; this just gives the user feedback)
    const stageTimers: number[] = [];
    const stageMessages = resumeLang === "zh"
      ? [
          { at: 5, msg: "📝 解析简历内容..." },
          { at: 20, msg: "🤖 LLM 生成内容..." },
          { at: 50, msg: "🎨 应用 CSS 样式..." },
          { at: 80, msg: "🌐 Chrome 转换 PDF..." },
          { at: 95, msg: "💾 保存文件..." },
        ]
      : [
          { at: 5, msg: "📝 Parsing resume..." },
          { at: 20, msg: "🤖 LLM generating content..." },
          { at: 50, msg: "🎨 Applying CSS styles..." },
          { at: 80, msg: "🌐 Chrome rendering PDF..." },
          { at: 95, msg: "💾 Saving file..." },
        ];

    stageTimers.push(
      window.setTimeout(() => {
        setGenProgress(5);
        setGenStage(stageMessages[0].msg);
      }, 500),
    );

    // Gradually progress through stages while waiting
    for (let i = 1; i < stageMessages.length; i++) {
      const stage = stageMessages[i];
      const prevAt = i > 0 ? stageMessages[i - 1].at : 0;
      const delay = ((stage.at - prevAt) / 95) * 1000; // Approximate
      stageTimers.push(
        window.setTimeout(() => {
          if (loading) {
            setGenProgress(stage.at);
            setGenStage(stage.msg);
          }
        }, 1000 + delay * 5),
      );
    }

    try {
      const result = await generateResume({
        api_key: apiKey,
        model_type: modelType,
        base_url: baseUrl,
        style_name: styleName,
        job_description: jobDesc || undefined,
        resume_language: resumeLang,
      });
      setGenProgress(100);
      setGenStage(resumeLang === "zh" ? "✅ 完成！" : "✅ Done!");
      setStatus(`${rt.success} ${result.filename}`);
      setDownloadFile(result.filename);
      // Auto-load the freshly generated HTML into the preview
      if (result.html_filename) {
        setDownloadHtmlFile(result.html_filename);
        setLoadingPreviewFile(result.html_filename);
        try {
          const preview = await previewSavedResume(result.html_filename);
          setPreviewHtml(preview.html);
          setPreviewKey((k) => k + 1);
          setStatus(`${rt.success} ${result.filename} (预览已更新)`);
        } catch (e) {
          console.warn("Failed to auto-load generated HTML for preview:", e);
        } finally {
          setLoadingPreviewFile("");
        }
      } else {
        setStatus(`${rt.success} ${result.filename}`);
      }
    } catch (err: any) {
      setGenProgress(-1);
      setGenStage("");
      setStatus(`${rt.error}: ${err.response?.data?.detail || err.message}`);
    } finally {
      stageTimers.forEach((t) => window.clearTimeout(t));
      // Keep progress visible for a moment to show completion
      window.setTimeout(() => {
        setLoading(false);
        setGenProgress(-1);
        setGenStage("");
      }, 1500);
    }
  };

  const handlePreview = async () => {
    if (!styleName) return;
    setPreviewing(true);
    try {
      const result = await previewResume({
        style_name: styleName,
        resume_language: resumeLang,
      });
      setPreviewHtml(result.html);
      setEditedHtml(result.html); // Sync edited buffer
      setSavedOk(false);
      setPreviewKey((k) => k + 1);
    } catch (err: any) {
      setStatus(`${rt.error}: ${err.response?.data?.detail || err.message}`);
      setPreviewHtml("");
    } finally {
      setPreviewing(false);
    }
  };

  const openPreviewInNewWindow = () => {
    if (!styleName) return;
    window.open(getPreviewPageUrl(styleName, resumeLang), "_blank");
  };

  const handleEditSave = (html: string) => {
    setEditedHtml(html);
    setSavedOk(true);
    setStatus(resumeLang === "zh" ? "✓ 编辑已保存（暂存于本地）" : "✓ Edits saved (local)");
    window.setTimeout(() => setSavedOk(false), 2500);
  };

  const handleExportEdited = () => {
    if (!editedHtml) return;
    // Trigger browser print to PDF, or download as HTML
    const blob = new Blob([editedHtml], { type: "text/html;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `resume_edited_${Date.now()}.html`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    setStatus(resumeLang === "zh" ? "✓ 已下载编辑版 HTML" : "✓ Edited HTML downloaded");
  };

  const handleEditReset = () => {
    setEditedHtml(previewHtml);
  };

  // Load history list (PDF + HTML files)
  const loadHistory = async () => {
    setLoadingHistory(true);
    try {
      const result = await getHistory();
      // Filter to PDF files only (HTML files are paired with them)
      const pdfs = (result.files as HistoryFile[]).filter((f) => f.name.endsWith(".pdf"));
      setHistoryFiles(pdfs);
    } catch (e) {
      console.warn("Failed to load history:", e);
    } finally {
      setLoadingHistory(false);
    }
  };

  // Preview a specific historical resume by loading its saved HTML
  const handlePreviewHistory = async (pdfFile: HistoryFile) => {
    // Build expected HTML filename: "resume_xxx.pdf" -> "resume_xxx.html"
    const htmlFilename = pdfFile.name.replace(/\.pdf$/, ".html");
    setLoadingPreviewFile(pdfFile.name);
    setHistoryOpen(false);
    try {
      const preview = await previewSavedResume(htmlFilename);
      setPreviewHtml(preview.html);
      setPreviewKey((k) => k + 1);
      setDownloadFile(pdfFile.name);
      setDownloadHtmlFile(htmlFilename);
      setStatus(
        (resumeLang === "zh"
          ? `✓ 已加载历史简历: ${pdfFile.name}`
          : `✓ Loaded historical resume: ${pdfFile.name}`),
      );
    } catch (e: any) {
      setStatus(
        (resumeLang === "zh"
          ? `⚠️ 加载历史简历失败: ${e.response?.data?.detail || e.message}`
          : `⚠️ Failed to load history: ${e.response?.data?.detail || e.message}`),
      );
    } finally {
      setLoadingPreviewFile("");
    }
  };

  return (
    <div className="page-enter max-w-7xl mx-auto">
      <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-6">{rt.title}</h2>

      {/* Three-column layout: Left config | Center preview | Right job desc */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Panel: Config + Style */}
        <div className="lg:col-span-3 space-y-4">
          {/* Config Card */}
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

          {/* Style Card */}
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

        {/* Center Panel: Preview (centered & prominent) */}
        <div className="lg:col-span-6 space-y-4">
          <div className="rounded-xl border border-gray-200 bg-white shadow-sm dark:border-gray-700 dark:bg-gray-800 flex flex-col">
            <div className="flex items-center justify-between border-b border-gray-200 px-5 py-3 dark:border-gray-700">
              <h3 className="flex items-center gap-2 text-sm font-semibold text-gray-700 dark:text-gray-300">
                <Eye className="h-4 w-4 text-brand-500" />
                {rt.preview}
                <span className="ml-2 rounded bg-gray-100 px-2 py-0.5 text-xs font-normal text-gray-600 dark:bg-gray-700 dark:text-gray-300">
                  {styleName || "-"}
                </span>
                {downloadHtmlFile && (
                  <span
                    className="ml-1 inline-flex items-center gap-1 rounded bg-gradient-to-r from-green-100 to-emerald-100 px-2 py-0.5 text-xs font-medium text-green-700 dark:from-green-900/40 dark:to-emerald-900/40 dark:text-green-300"
                    title={downloadHtmlFile}
                  >
                    <Sparkle className="h-3 w-3" /> 最新生成
                  </span>
                )}
              </h3>
              <div className="flex items-center gap-2">
                <button
                  onClick={handlePreview}
                  disabled={previewing || !styleName}
                  className="inline-flex items-center gap-1 rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-200 dark:hover:bg-gray-600"
                  title={rt.previewRefresh}
                >
                  <RefreshCw className={`h-3 w-3 ${previewing ? "animate-spin" : ""}`} />
                  <span className="hidden sm:inline">{rt.previewRefresh}</span>
                </button>
                <button
                  onClick={openPreviewInNewWindow}
                  disabled={!styleName}
                  className="inline-flex items-center gap-1 rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-200 dark:hover:bg-gray-600"
                  title={rt.previewOpen}
                >
                  <ExternalLink className="h-3 w-3" />
                  <span className="hidden sm:inline">{rt.previewOpen}</span>
                </button>
              </div>
            </div>

            <p className="px-5 pt-3 text-xs text-gray-500 dark:text-gray-400">
              {editMode
                ? (resumeLang === "zh"
                    ? "✏️ 编辑模式：直接在下方修改文字、格式、列表等"
                    : "✏️ Edit mode: modify text, formatting, lists, etc. below")
                : rt.previewHint}
            </p>

            {/* Mode toggle buttons + history picker */}
            <div className="flex flex-wrap items-center justify-end gap-2 px-5 pt-2">
              {/* History picker */}
              <div className="relative">
                <button
                  type="button"
                  onClick={() => {
                    if (!historyOpen) loadHistory();
                    setHistoryOpen((o) => !o);
                  }}
                  className="inline-flex items-center gap-1 rounded-lg border border-gray-300 bg-white px-2.5 py-1 text-xs font-medium text-gray-700 transition-colors hover:bg-gray-50 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-200 dark:hover:bg-gray-600"
                  title="加载历史生成的简历"
                >
                  <HistoryIcon className="h-3 w-3" /> 历史
                </button>
                {historyOpen && (
                  <div className="absolute right-0 top-full z-20 mt-1 w-80 max-h-72 overflow-y-auto rounded-lg border border-gray-200 bg-white shadow-xl dark:border-gray-700 dark:bg-gray-800">
                    <div className="sticky top-0 flex items-center justify-between border-b border-gray-100 bg-white px-3 py-2 text-xs font-semibold text-gray-700 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200">
                      <span>历史简历 ({historyFiles.length})</span>
                      <button
                        type="button"
                        onClick={loadHistory}
                        disabled={loadingHistory}
                        className="text-brand-600 hover:text-brand-700 disabled:opacity-50"
                      >
                        <RefreshCw className={`h-3 w-3 ${loadingHistory ? "animate-spin" : ""}`} />
                      </button>
                    </div>
                    {loadingHistory ? (
                      <div className="flex items-center justify-center p-6 text-xs text-gray-500">
                        <LoadingSpinner size="sm" />
                        <span className="ml-2">加载中...</span>
                      </div>
                    ) : historyFiles.length === 0 ? (
                      <div className="p-6 text-center text-xs text-gray-500">暂无历史简历</div>
                    ) : (
                      <ul className="divide-y divide-gray-100 dark:divide-gray-700">
                        {historyFiles.slice(0, 15).map((file) => (
                          <li key={file.name}>
                            <button
                              type="button"
                              onClick={() => handlePreviewHistory(file)}
                              disabled={loadingPreviewFile === file.name}
                              className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs hover:bg-gray-50 disabled:cursor-wait disabled:opacity-60 dark:hover:bg-gray-700"
                            >
                              <FileText className="h-3.5 w-3.5 flex-shrink-0 text-brand-500" />
                              <div className="min-w-0 flex-1">
                                <p className="truncate font-medium text-gray-900 dark:text-white">{file.name}</p>
                                <p className="text-[10px] text-gray-500 dark:text-gray-400">{file.modified}</p>
                              </div>
                              {loadingPreviewFile === file.name && (
                                <RefreshCw className="h-3 w-3 animate-spin text-brand-500" />
                              )}
                            </button>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
              </div>

              <div className="inline-flex rounded-lg border border-gray-200 bg-gray-50 p-0.5 dark:border-gray-600 dark:bg-gray-900">
                <button
                  type="button"
                  onClick={() => setEditMode(false)}
                  className={`inline-flex items-center gap-1 rounded px-2.5 py-1 text-xs font-medium transition-colors ${
                    !editMode
                      ? "bg-white text-gray-900 shadow-sm dark:bg-gray-700 dark:text-white"
                      : "text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
                  }`}
                  title="预览模式（只读）"
                >
                  <Eye className="h-3 w-3" /> 预览
                </button>
                <button
                  type="button"
                  onClick={() => setEditMode(true)}
                  disabled={!previewHtml}
                  className={`inline-flex items-center gap-1 rounded px-2.5 py-1 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                    editMode
                      ? "bg-white text-gray-900 shadow-sm dark:bg-gray-700 dark:text-white"
                      : "text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
                  }`}
                  title="编辑模式（可修改）"
                >
                  <Edit3 className="h-3 w-3" /> 编辑
                </button>
              </div>

              {editMode && (
                <>
                  <button
                    type="button"
                    onClick={handleEditReset}
                    disabled={editedHtml === previewHtml}
                    className="inline-flex items-center gap-1 rounded-lg border border-gray-300 bg-white px-2.5 py-1 text-xs font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-200 dark:hover:bg-gray-600"
                    title="放弃编辑，恢复 LLM 原始内容"
                  >
                    <RotateCcw className="h-3 w-3" /> 撤销编辑
                  </button>
                  <button
                    type="button"
                    onClick={handleExportEdited}
                    disabled={!editedHtml}
                    className="inline-flex items-center gap-1 rounded-lg border border-brand-300 bg-brand-50 px-2.5 py-1 text-xs font-medium text-brand-700 transition-colors hover:bg-brand-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-brand-700 dark:bg-brand-900/30 dark:text-brand-300"
                    title="下载编辑版 HTML"
                  >
                    <Download className="h-3 w-3" /> 导出 HTML
                  </button>
                </>
              )}

              {savedOk && (
                <span className="inline-flex items-center gap-1 text-xs text-green-600">
                  <Check className="h-3 w-3" /> 已保存
                </span>
              )}
            </div>

            {/* Preview / Editor area */}
            <div className="flex-1 p-5">
              <div className="mx-auto max-w-3xl overflow-hidden rounded-lg border border-gray-200 bg-gray-50 shadow-inner dark:border-gray-600 dark:bg-gray-900">
                {previewing && !previewHtml ? (
                  <div className="flex h-[700px] items-center justify-center">
                    <LoadingSpinner />
                    <span className="ml-2 text-sm text-gray-500">{rt.previewing}</span>
                  </div>
                ) : previewHtml && editMode ? (
                  <EditableResumePreview
                    key={previewKey}
                    initialHtml={previewHtml}
                    onSave={handleEditSave}
                    onChange={(html) => setEditedHtml(html)}
                    placeholder={rt.previewEmpty}
                  />
                ) : previewHtml ? (
                  <iframe
                    key={previewKey}
                    ref={previewRef}
                    srcDoc={previewHtml}
                    title="Resume Preview"
                    className="h-[700px] w-full bg-white"
                    sandbox="allow-same-origin"
                  />
                ) : (
                  <div className="flex h-[700px] items-center justify-center text-sm text-gray-500">
                    {rt.previewEmpty}
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Action bar below preview */}
          <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
              <button
                onClick={handleGenerate}
                disabled={loading}
                className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-brand-600 to-brand-700 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-brand-500/25 transition-all hover:from-brand-700 hover:to-brand-800 hover:shadow-xl disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading ? <LoadingSpinner size="sm" /> : <Sparkles className="h-4 w-4" />}
                {loading ? rt.generating : rt.generate}
              </button>

              {downloadFile && (
                <a
                  href={getDownloadUrl(downloadFile)}
                  download
                  className="flex items-center justify-center gap-2 rounded-xl border border-brand-200 bg-brand-50 px-5 py-3 text-sm font-medium text-brand-700 transition-colors hover:bg-brand-100 dark:border-brand-800 dark:bg-brand-900/20 dark:text-brand-300"
                >
                  <Download className="h-4 w-4" />
                  {rt.download}
                </a>
              )}
            </div>

            {/* Progress bar */}
            {loading && genProgress >= 0 && (
              <div className="mt-3">
                <div className="mb-1.5 flex items-center justify-between text-xs">
                  <span className="font-medium text-gray-700 dark:text-gray-300">{genStage}</span>
                  <span className="font-mono text-gray-500 dark:text-gray-400">{genProgress}%</span>
                </div>
                <div className="h-2 w-full overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-brand-500 to-brand-700 transition-all duration-500 ease-out"
                    style={{ width: `${genProgress}%` }}
                  />
                </div>
                <p className="mt-1.5 text-[11px] text-gray-400 dark:text-gray-500">
                  {resumeLang === "zh"
                    ? "💡 生成通常需要 30-60 秒，请耐心等待"
                    : "💡 Generation typically takes 30-60s, please be patient"}
                </p>
              </div>
            )}

            {status && (
              <div
                className={`mt-3 rounded-xl border p-3 text-sm ${
                  status.includes("成功") || status.includes("success")
                    ? "border-green-200 bg-green-50 text-green-800 dark:border-green-800 dark:bg-green-900/20 dark:text-green-300"
                    : status.includes("失败") || status.includes("error") || status.includes("Error")
                    ? "border-red-200 bg-red-50 text-red-800 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300"
                    : "border-blue-200 bg-blue-50 text-blue-800 dark:border-blue-800 dark:bg-blue-900/20 dark:text-blue-300"
                }`}
              >
                {status}
              </div>
            )}
          </div>
        </div>

        {/* Right Panel: Job Description */}
        <div className="lg:col-span-3 space-y-4">
          <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-700 dark:bg-gray-800">
            <label className="mb-2 flex items-center gap-2 text-sm font-semibold text-gray-700 dark:text-gray-300">
              <FileText className="h-4 w-4 text-brand-500" />
              {rt.jobDesc}
            </label>
            <textarea
              value={jobDesc}
              onChange={(e) => setJobDesc(e.target.value)}
              placeholder={rt.jobDescPlaceholder}
              rows={14}
              className="w-full rounded-lg border border-gray-300 px-4 py-3 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500 dark:border-gray-600 dark:bg-gray-700 dark:text-white resize-none"
            />
            <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
              {resumeLang === "zh" ? "可选 - 提供 JD 以生成定制简历" : "Optional - provide JD for tailored resume"}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
