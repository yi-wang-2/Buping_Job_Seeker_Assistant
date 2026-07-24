import { useState, useEffect, useRef, useCallback } from "react";
import { Download, Sparkles, Palette, Eye, ExternalLink, RefreshCw, FileText, Edit3, Save, RotateCcw, Check, History as HistoryIcon, Sparkle } from "lucide-react";
import type { Strings } from "../i18n";
import { useSessionState } from "../hooks/useSessionState";
import { getStyles, generateResume, getDownloadUrl, previewResume, getPreviewPageUrl, getHistory, previewSavedResume, getSettings, saveSettings, saveEditedResume } from "../api/client";
import LoadingSpinner from "../components/LoadingSpinner";
import AIRewriteDialog from "../components/AIRewriteDialog";
import { EditableResumePreview } from "../components/editor";
import { useAvailableModels } from "../hooks/useAvailableModels";

// Preset list of supported LLM providers — kept in sync with Settings page.
// Choosing a preset auto-fills base_url AND protocol fields.
type LlmProtocol = "anthropic" | "openai_chat" | "openai_response";

interface ModelPreset {
  id: string;
  label: string;
  defaultBaseUrl: string;
  protocol: LlmProtocol;
}

const MODEL_PRESETS: ReadonlyArray<ModelPreset> = [
  // Anthropic Messages protocol
  { id: "anthropic",     label: "Anthropic (Claude 官方)",          defaultBaseUrl: "https://api.anthropic.com",        protocol: "anthropic" },
  { id: "minimax-anth",  label: "MiniMax (Anthropic 协议)",        defaultBaseUrl: "https://api.minimaxi.com/anthropic", protocol: "anthropic" },
  // OpenAI Chat Completions protocol
  { id: "openai",        label: "OpenAI (Chat Completions)",       defaultBaseUrl: "https://api.openai.com/v1",           protocol: "openai_chat" },
  { id: "deepseek",      label: "DeepSeek",                        defaultBaseUrl: "https://api.deepseek.com/v1",        protocol: "openai_chat" },
  { id: "zhipu",         label: "智谱 AI (GLM-4)",                  defaultBaseUrl: "https://open.bigmodel.cn/api/paas/v4", protocol: "openai_chat" },
  { id: "moonshot",      label: "月之暗面 (Kimi)",                  defaultBaseUrl: "https://api.moonshot.cn/v1",         protocol: "openai_chat" },
  { id: "qwen",          label: "通义千问 (Qwen)",                  defaultBaseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1", protocol: "openai_chat" },
  { id: "doubao",        label: "豆包 (Doubao)",                    defaultBaseUrl: "https://ark.cn-beijing.volces.com/api/v3", protocol: "openai_chat" },
  { id: "yi",            label: "零一万物 (Yi)",                    defaultBaseUrl: "https://api.lingyiwanwu.com/v1",    protocol: "openai_chat" },
  { id: "minimax-chat",  label: "MiniMax (OpenAI Chat 协议)",      defaultBaseUrl: "https://api.minimaxi.com/v1",        protocol: "openai_chat" },
  { id: "ollama",        label: "Ollama (本地)",                    defaultBaseUrl: "http://localhost:11434/v1",        protocol: "openai_chat" },
  // OpenAI Responses API
  { id: "openai-resp",   label: "OpenAI (Responses API)",          defaultBaseUrl: "https://api.openai.com/v1",           protocol: "openai_response" },
  { id: "minimax-resp",  label: "MiniMax (Responses API)",         defaultBaseUrl: "https://api.minimaxi.com/v1",        protocol: "openai_response" },
];

const PRESET_BY_ID: Record<string, ModelPreset> = Object.fromEntries(
  MODEL_PRESETS.map((p) => [p.id, p])
);
const DEFAULT_MODEL_BY_PROVIDER: Record<string, string> = {
  anthropic: "claude-sonnet-4-20250514", "minimax-anth": "MiniMax-M3",
  openai: "gpt-4o-mini", deepseek: "deepseek-chat", zhipu: "glm-4-flash",
  moonshot: "moonshot-v1-8k", qwen: "qwen-plus", yi: "yi-lightning",
  "minimax-chat": "MiniMax-M3", "openai-resp": "gpt-4o-mini", "minimax-resp": "MiniMax-M3",
};

interface HistoryFile {
  name: string;
  path: string;
  size: number;
  modified: string;
}

/**
 * Walk the document subtree and replace the first occurrence of
 * `searchText` (across text node boundaries) with `replaceText`.
 * Returns true if a replacement was made.
 *
 * Why this exists: when user selects text in the WYSIWYG iframe, the
 * selection is plain text, but the document HTML contains tags. A
 * naive `source.split(searchText).join(replaceText)` only works when
 * the selected text happens to span no formatting — which is rare.
 *
 * Strategy: use a TreeWalker to scan all text nodes in document order,
 * concatenating them into a flat string with index map, find the
 * substring, then re-split nodes at the match boundaries and replace.
 */
function replaceFirstTextOccurrence(
  root: HTMLElement,
  searchText: string,
  replaceText: string,
): boolean {
  if (!searchText || !replaceText) return false;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
  // Include ALL text nodes (even whitespace-only) to preserve
  // structural info. We collapse whitespace in the search index below.
  const textNodes: Text[] = [];
  let node: Node | null;
  while ((node = walker.nextNode())) {
    textNodes.push(node as Text);
  }
  if (textNodes.length === 0) return false;

  // Build concatenated string + a parallel "collapsed" string with
  // whitespace collapsed to single spaces. The search runs against
  // the collapsed version so leading/trailing whitespace differences
  // between user selection and source text don't break the match.
  const concatParts: string[] = [];
  const indexMap: Array<{ node: Text; start: number; end: number }> = [];
  for (const tn of textNodes) {
    const start = concatParts.join("").length;
    concatParts.push(tn.nodeValue || "");
    indexMap.push({ node: tn, start, end: start + (tn.nodeValue || "").length });
  }
  const concat = concatParts.join("");

  // collapsedToOriginal[i] = index in `concat` of the i-th non-whitespace
  // (or single-space) character in the collapsed version.
  const collapsedChars: string[] = [];
  const collapsedToOriginal: number[] = [];
  let lastWasSpace = false;
  for (let i = 0; i < concat.length; i++) {
    const isSpace = /\s/.test(concat[i]);
    if (isSpace) {
      if (!lastWasSpace && collapsedChars.length > 0) {
        collapsedChars.push(" ");
        collapsedToOriginal.push(i);
        lastWasSpace = true;
      }
    } else {
      collapsedChars.push(concat[i]);
      collapsedToOriginal.push(i);
      lastWasSpace = false;
    }
  }
  const collapsedStr = collapsedChars.join("");

  // Normalize search text (collapse whitespace, trim) the same way
  const searchNormalized = searchText.replace(/\s+/g, " ").trim();
  if (!searchNormalized) return false;

  const matchIdx = collapsedStr.indexOf(searchNormalized);
  if (matchIdx < 0) return false;
  const matchEnd = matchIdx + searchNormalized.length;

  // Map collapsed indices back to original concat indices
  const originalStart = collapsedToOriginal[matchIdx];
  const originalEnd =
    matchEnd < collapsedToOriginal.length
      ? collapsedToOriginal[matchEnd]
      : concat.length;

  // Find the text nodes that contain the original-match start and end
  const startEntry = indexMap.find((e) => originalStart < e.end);
  const endEntry = indexMap.find((e) => originalEnd <= e.end);
  if (!startEntry || !endEntry) return false;

  const startOffsetInStartNode = originalStart - startEntry.start;
  const endOffsetInEndNode = originalEnd - endEntry.start;

  if (startEntry.node === endEntry.node) {
    // Simple case: match within a single text node
    const tn = startEntry.node;
    const before = tn.nodeValue!.substring(0, startOffsetInStartNode);
    const after = tn.nodeValue!.substring(endOffsetInEndNode);
    tn.nodeValue = before + replaceText + after;
  } else {
    // Match spans multiple text nodes. Rewrite the first node to contain
    // the prefix + replacement, the last node to contain the suffix,
    // and remove the in-between text nodes.
    const firstNode = startEntry.node;
    const lastNode = endEntry.node;
    const before = firstNode.nodeValue!.substring(0, startOffsetInStartNode);
    const after = lastNode.nodeValue!.substring(endOffsetInEndNode);
    firstNode.nodeValue = before + replaceText + after;
    // Remove all nodes between first and last
    let cur: Node | null = firstNode.nextSibling;
    while (cur && cur !== lastNode) {
      const next: Node | null = cur.nextSibling;
      cur.parentNode?.removeChild(cur);
      cur = next;
    }
    if (lastNode.parentNode) {
      lastNode.parentNode.removeChild(lastNode);
    }
  }

  return true;
}

export default function ResumeGenerate({ t }: { t: Strings }) {
  const rt = t.resume;
  const [styles, setStyles] = useState<Record<string, { file: string; author: string }>>({});
  const [apiKey, setApiKey] = useState("");
  const [modelType, setModelType] = useState("anthropic");
  const [modelName, setModelName] = useState("MiniMax-M3");
  const [baseUrl, setBaseUrl] = useState("https://api.minimaxi.com/anthropic");
  const [llmProtocol, setLlmProtocol] = useState<LlmProtocol>("anthropic");
  const availableModels = useAvailableModels(apiKey, baseUrl, llmProtocol);
  const [styleName, setStyleName] = useSessionState("buping_resume_style", "");
  const [jobDesc, setJobDesc] = useSessionState("buping_resume_job_desc", "");
  const [resumeLang, setResumeLang] = useState("zh");
  const [systemLanguage, setSystemLanguage] = useState("zh");
  const [configSaveStatus, setConfigSaveStatus] = useState("");
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useSessionState("buping_resume_status", "");
  const [downloadFile, setDownloadFile] = useSessionState("buping_resume_download_pdf", "");
  const [downloadHtmlFile, setDownloadHtmlFile] = useSessionState<string>("buping_resume_download_html", ""); // e.g. "resume_20250615_103045.html"
  // Generation progress state (0-100, -1 = idle, stage label)
  const [genProgress, setGenProgress] = useState<number>(-1);
  const [genStage, setGenStage] = useState<string>("");

  // Preview state
  const [previewing, setPreviewing] = useState(false);
  const [previewHtml, setPreviewHtml] = useSessionState<string>("buping_resume_preview_html", "");
  const [previewKey, setPreviewKey] = useState<number>(0);
  const skipRestoredPreviewRef = useRef(Boolean(previewHtml));
  const previewRef = useRef<HTMLIFrameElement | null>(null);

  // History picker
  const [historyFiles, setHistoryFiles] = useState<HistoryFile[]>([]);
  const [historyOpen, setHistoryOpen] = useState<boolean>(false);
  const [loadingHistory, setLoadingHistory] = useState<boolean>(false);
  const [loadingPreviewFile, setLoadingPreviewFile] = useState<string>(""); // currently loading filename

  // Edit mode state
  const [editMode, setEditMode] = useSessionState<boolean>("buping_resume_edit_mode", false);
  const [editedHtml, setEditedHtml] = useSessionState<string>("buping_resume_edited_html", "");
  const [savedOk, setSavedOk] = useSessionState<boolean>("buping_resume_saved_ok", false);
  const [saving, setSaving] = useState<boolean>(false);

  // AI Rewrite state (Roadmap §1)
  const [rewriteDialogOpen, setRewriteDialogOpen] = useState<boolean>(false);
  const [selectedText, setSelectedText] = useState<string>("");
  const [surroundingContext, setSurroundingContext] = useState<string>("");
  // Last selection captured from the editor (for the toolbar button)
  const [lastSelection, setLastSelection] = useState<string>("");
  // The WYSIWYG iframe's element (set by EditableResumePreview via onIframeReady).
  // Used by handleApplyRewrite to mutate the document directly.
  const [editorIframe, setEditorIframe] = useState<HTMLIFrameElement | null>(null);

  // Backend warmup — track whether styles/settings loaded successfully
  const [stylesError, setStylesError] = useState<string>("");

  // Retry helper used by both mount and the "重试" button.
  // Uses a ref for styleName to avoid recreating the callback when the
  // style changes (which would cause an infinite loop with the mount
  // useEffect).
  const styleNameRef = useRef(styleName);
  styleNameRef.current = styleName;

  const loadStylesAndSettings = useCallback(() => {
    setStylesError("");
    let stylesLoaded = false;
    let settingsLoaded = false;

    const finishOne = () => {
      // Once both calls have settled, show retry button if styles failed.
      if (stylesLoaded && settingsLoaded) {
        setStylesError("");
      } else if (!stylesLoaded && !settingsLoaded) {
        // Both failed — show error
        setStylesError(
          resumeLang === "zh"
            ? "样式加载失败，点重试"
            : "Styles failed to load. Click retry.",
        );
      }
      // If only one failed, leave the existing error state intact
      // (or cleared if previously set). The user's manual retry will
      // re-run both calls.
    };

    getStyles()
      .then((s) => {
        stylesLoaded = true;
        setStyles(s);
        const keys = Object.keys(s);
        if (keys.length > 0 && !styleNameRef.current) {
          setStyleName(keys[0]);
        }
      })
      .catch((e) => {
        console.warn("Failed to load styles:", e?.message || e);
      })
      .finally(finishOne);

    // Always overwrite defaults with backend-saved settings — even if
    // the saved value is an empty string (user explicitly cleared it).
    getSettings()
      .then((cfg) => {
        settingsLoaded = true;
        setApiKey(cfg.llm_api_key ?? "");
        setModelType(cfg.llm_model_type || "anthropic");
        setModelName(cfg.llm_model || DEFAULT_MODEL_BY_PROVIDER[cfg.llm_model_type] || "");
        setBaseUrl(cfg.llm_base_url || "https://api.minimaxi.com/anthropic");
        setLlmProtocol((cfg.llm_protocol as LlmProtocol) || "anthropic");
        setResumeLang(cfg.resume_language || "zh");
        setSystemLanguage(cfg.system_language || "zh");
      })
      .catch((e) => console.warn("Failed to load saved settings:", e))
      .finally(finishOne);
  }, [resumeLang]); // intentionally omit styleName

  useEffect(() => {
    loadStylesAndSettings();
  }, [loadStylesAndSettings]);

  // Fallback: if the styles list is still empty after 8 seconds (e.g.
  // axios interceptor's 4-retry sequence ran out while backend was
  // still warming up), poll once more. This handles the rare case of
  // very slow backend startup (Chrome driver + model import can take
  // 5-10s on first launch).
  useEffect(() => {
    const timer = window.setTimeout(() => {
      if (Object.keys(styles).length === 0) {
        console.warn("Styles still empty after 8s, polling once more");
        loadStylesAndSettings();
      }
    }, 8000);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadStylesAndSettings]);

  useEffect(() => {
    if (skipRestoredPreviewRef.current) {
      skipRestoredPreviewRef.current = false;
      return;
    }
    if (styleName && resumeLang) {
      handlePreview();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [styleName, resumeLang]);

  const handleSaveLlmConfig = async () => {
    try {
      await saveSettings({
        llm_api_key: apiKey,
        llm_model_type: modelType,
        llm_model: modelName.trim(),
        llm_base_url: baseUrl,
        llm_protocol: llmProtocol,
        resume_language: resumeLang,
        system_language: systemLanguage,
      });
      setConfigSaveStatus(resumeLang === "zh" ? "配置已保存" : "Configuration saved");
      window.setTimeout(() => setConfigSaveStatus(""), 3000);
    } catch (err: any) {
      setConfigSaveStatus(err?.response?.data?.detail || err?.message || "Save failed");
    }
  };

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
        model_name: modelName,
        base_url: baseUrl,
        llm_protocol: llmProtocol,
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

  const handleEditSave = async (html: string) => {
    setEditedHtml(html);
    setSavedOk(true);
    setStatus(
      resumeLang === "zh"
        ? "✓ 已保存到历史记录（含 PDF + HTML）"
        : "✓ Saved to history (PDF + HTML)",
    );
    window.setTimeout(() => setSavedOk(false), 2500);

    // Render the edited HTML to PDF + save pair on the backend so the
    // new version appears in the history list. This also reuses the
    // same HTML as the new `previewHtml` so switching back to preview
    // mode shows the latest edits (and re-opening the editor reloads
    // from the latest saved HTML).
    setSaving(true);
    try {
      const result = await saveEditedResume(html, "resume_edited");
      if (result.status === "success") {
        setPreviewHtml(html);
        setPreviewKey((k) => k + 1);
        setDownloadFile(result.pdf_filename);
        setDownloadHtmlFile(result.html_filename);
        setStatus(
          resumeLang === "zh"
            ? `✓ 已保存：${result.pdf_filename}（可在历史记录中查看）`
            : `✓ Saved: ${result.pdf_filename} (visible in history)`,
        );
      }
    } catch (err: any) {
      setStatus(
        resumeLang === "zh"
          ? `⚠️ 后端保存失败：${err?.response?.data?.detail || err?.message || "未知错误"}`
          : `⚠️ Backend save failed: ${err?.response?.data?.detail || err?.message || "Unknown error"}`,
      );
    } finally {
      setSaving(false);
    }
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

  // AI Rewrite — open dialog with current selection
  const handleOpenRewrite = (text: string) => {
    if (!text || !text.trim()) {
      setStatus(resumeLang === "zh" ? "⚠️ 请先在编辑器中选中需要改写的文本" : "⚠️ Select text first");
      return;
    }
    setSelectedText(text);
    // Build a context window: a small slice of the surrounding editedHtml
    // so the LLM can see how the selected text fits in the resume.
    const fullHtml = editedHtml || previewHtml || "";
    if (fullHtml && text.length > 0) {
      const idx = fullHtml.indexOf(text);
      if (idx >= 0) {
        const before = fullHtml.slice(Math.max(0, idx - 300), idx);
        const after = fullHtml.slice(idx + text.length, idx + text.length + 300);
        setSurroundingContext(`${before}⟨SELECTION⟩${after}`);
      } else {
        setSurroundingContext("");
      }
    } else {
      setSurroundingContext("");
    }
    setRewriteDialogOpen(true);
  };

  // AI Rewrite — apply the rewritten text by mutating the iframe body
  // directly (the parent state mirrors the mutation via the iframe's
  // input event listener). This preserves rich-text formatting and avoids
  // the "selected text vs HTML source" mismatch that breaks find-and-replace.
  const handleApplyRewrite = (rewritten: string) => {
    if (!selectedText || !rewritten) return;
    const doc = editorIframe?.contentDocument;
    if (!doc) {
      setStatus(
        resumeLang === "zh"
          ? "⚠️ 无法定位编辑器，请重试"
          : "⚠️ Cannot locate editor, please retry",
      );
      setRewriteDialogOpen(false);
      return;
    }
    const replaced = replaceFirstTextOccurrence(doc.body, selectedText, rewritten);
    if (!replaced) {
      setStatus(
        resumeLang === "zh"
          ? "⚠️ 选中文本在文档中未找到（可能被格式化分散）"
          : "⚠️ Selected text not found (may be split by formatting)",
      );
      setRewriteDialogOpen(false);
      return;
    }
    // Trigger input event so the iframe's onChange handler fires and
    // updates parent state via the existing `onChange` callback.
    doc.dispatchEvent(new Event("input", { bubbles: true }));
    setRewriteDialogOpen(false);
    setStatus(
      resumeLang === "zh"
        ? "✓ 已应用 AI 改写（记得保存到本地或下载）"
        : "✓ Rewrite applied (save or download to persist)",
    );
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
                  onChange={(e) => {
                    const newType = e.target.value;
                    setModelType(newType);
                    // Auto-fill base_url AND protocol when picking a preset
                    const preset = PRESET_BY_ID[newType];
                    if (preset) {
                      setBaseUrl(preset.defaultBaseUrl);
                      setLlmProtocol(preset.protocol);
                      setModelName(DEFAULT_MODEL_BY_PROVIDER[newType] || "");
                    }
                  }}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none dark:border-gray-600 dark:bg-gray-700 dark:text-white"
                >
                  {MODEL_PRESETS.map((preset) => (
                    <option key={preset.id} value={preset.id}>
                      {preset.label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">模型名称 / Model ID</label>
                {availableModels.length > 0 && (
                  <select
                    value={availableModels.includes(modelName) ? modelName : ""}
                    onChange={(e) => e.target.value && setModelName(e.target.value)}
                    className="mb-2 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none dark:border-gray-600 dark:bg-gray-700 dark:text-white"
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
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500 dark:border-gray-600 dark:bg-gray-700 dark:text-white"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">{rt.modelProtocol}</label>
                <select
                  value={llmProtocol}
                  onChange={(e) => setLlmProtocol(e.target.value as LlmProtocol)}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none dark:border-gray-600 dark:bg-gray-700 dark:text-white"
                >
                  <option value="anthropic">{rt.protocolAnthropic}</option>
                  <option value="openai_chat">{rt.protocolOpenaiChat}</option>
                  <option value="openai_response">{rt.protocolOpenaiResponse}</option>
                </select>
                {llmProtocol === "openai_response" && (
                  <p className="mt-2 rounded-md bg-amber-50 px-2 py-1.5 text-xs text-amber-700 dark:bg-amber-900/20 dark:text-amber-300">
                    Responses API 需要供应商及客户端同时支持；系统会按当前选择发送，不会自动切换。
                  </p>
                )}
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
              <div className="flex items-center gap-3 pt-1">
                <button
                  type="button"
                  onClick={handleSaveLlmConfig}
                  className="flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-brand-700"
                >
                  <Save className="h-4 w-4" />
                  {resumeLang === "zh" ? "保存 LLM 配置" : "Save LLM config"}
                </button>
                {configSaveStatus && (
                  <span className="text-xs text-gray-600 dark:text-gray-300">{configSaveStatus}</span>
                )}
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
                <div className="space-y-2">
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    {stylesError
                      ? stylesError
                      : resumeLang === "zh"
                      ? "正在加载样式..."
                      : "Loading styles..."}
                  </p>
                  {stylesError && (
                    <button
                      type="button"
                      onClick={loadStylesAndSettings}
                      className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-brand-700"
                    >
                      <RefreshCw className="h-3.5 w-3.5" />
                      {resumeLang === "zh" ? "重试" : "Retry"}
                    </button>
                  )}
                </div>
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
                    onClick={() => handleOpenRewrite(lastSelection)}
                    disabled={!lastSelection || !lastSelection.trim()}
                    className="inline-flex items-center gap-1 rounded-lg border border-brand-300 bg-brand-50 px-2.5 py-1 text-xs font-medium text-brand-700 transition-colors hover:bg-brand-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-brand-700 dark:bg-brand-900/30 dark:text-brand-300"
                    title="AI 智能改写（先在编辑器中选中文字）"
                  >
                    <Sparkles className="h-3 w-3" /> AI 改写
                  </button>
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

              {editMode && lastSelection && lastSelection.trim() && (
                <span className="inline-flex items-center gap-1 text-xs text-brand-600 dark:text-brand-400">
                  <Sparkles className="h-3 w-3" />
                  {resumeLang === "zh"
                    ? `已选中 ${lastSelection.length} 字 — 点 AI 改写`
                    : `Selected ${lastSelection.length} chars — click AI Rewrite`}
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
                    // Stable initialHtml — typing only flows through
                    // onChange (no iframe reload, preserves cursor).
                    // AI rewrite mutates the iframe body directly via
                    // editorIframe ref + onIframeReady callback.
                    key={`editor-${previewKey}`}
                    initialHtml={previewHtml}
                    onSave={handleEditSave}
                    onChange={(html) => setEditedHtml(html)}
                    onSelectionChange={(text) => setLastSelection(text)}
                    onIframeReady={setEditorIframe}
                    saving={saving}
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

      {/* AI Rewrite Dialog (Roadmap §1) */}
      <AIRewriteDialog
        isOpen={rewriteDialogOpen}
        selectedText={selectedText}
        surroundingContext={surroundingContext}
        targetLanguage={resumeLang === "en" ? "en" : "zh"}
        apiKey={apiKey}
        modelType={modelType}
        modelName={modelName}
        baseUrl={baseUrl}
        llmProtocol={llmProtocol}
        t={t}
        onApply={handleApplyRewrite}
        onClose={() => setRewriteDialogOpen(false)}
      />
    </div>
  );
}
