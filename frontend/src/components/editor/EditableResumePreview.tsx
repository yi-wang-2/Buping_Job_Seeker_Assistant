import { useState, useEffect, useRef, useMemo } from "react";
import {
  Undo,
  Redo,
  Bold,
  Italic,
  Underline as UnderlineIcon,
  Strikethrough,
  List,
  ListOrdered,
  Quote,
  Link as LinkIcon,
  Code,
  Heading1,
  Heading2,
  Heading3,
  Minus,
  Unlink,
} from "lucide-react";
import { extractStyleFromHtml } from "./extractStyle";

interface EditableResumePreviewProps {
  initialHtml: string;
  onSave?: (html: string) => void;
  onChange?: (html: string) => void;
  onSelectionChange?: (text: string) => void;
  onReset?: () => void;
  placeholder?: string;
  className?: string;
  showSaveButton?: boolean;
  showResetButton?: boolean;
  showAutoSave?: boolean;
}

export default function EditableResumePreview({
  initialHtml,
  onSave,
  onChange,
  onSelectionChange,
  onReset,
  placeholder = "开始编辑你的简历...",
  className = "",
  showSaveButton = true,
  showResetButton = true,
  showAutoSave = true,
}: EditableResumePreviewProps) {
  const [currentHtml, setCurrentHtml] = useState(initialHtml);
  const [isDirty, setIsDirty] = useState(false);
  const [autoSaved, setAutoSaved] = useState<Date | null>(null);
  const debounceRef = useRef<number | null>(null);

  useEffect(() => {
    setIsDirty(currentHtml !== initialHtml);
  }, [currentHtml, initialHtml]);

  useEffect(() => {
    if (!isDirty || !showAutoSave) return;
    if (debounceRef.current) {
      window.clearTimeout(debounceRef.current);
    }
    debounceRef.current = window.setTimeout(() => {
      try {
        const key = `resume_edit_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
        localStorage.setItem(key, currentHtml);
        const allKeys = Object.keys(localStorage).filter((k) => k.startsWith("resume_edit_"));
        if (allKeys.length > 5) {
          allKeys
            .sort()
            .slice(0, allKeys.length - 5)
            .forEach((k) => localStorage.removeItem(k));
        }
        setAutoSaved(new Date());
      } catch (e) {
        console.warn("Auto-save failed:", e);
      }
    }, 1500);
    return () => {
      if (debounceRef.current) window.clearTimeout(debounceRef.current);
    };
  }, [currentHtml, isDirty, showAutoSave]);

  const handleChange = (html: string) => {
    setCurrentHtml(html);
    onChange?.(html);
  };

  const handleSave = () => {
    onSave?.(currentHtml);
  };

  const handleReset = () => {
    if (
      window.confirm(
        "确定要放弃所有修改，恢复到原始 LLM 生成的内容吗？"
      )
    ) {
      setCurrentHtml(initialHtml);
      onReset?.();
    }
  };

  return (
    <div className={className}>
      <EditableWYSIWYGEditor
        initialHtml={initialHtml}
        currentHtml={currentHtml}
        placeholder={placeholder}
        onChange={handleChange}
        onSelectionChange={onSelectionChange}
      />

      <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs">
        <div className="flex items-center gap-2 text-gray-500 dark:text-gray-400">
          {isDirty ? (
            <>
              <span className="inline-block h-2 w-2 rounded-full bg-amber-500" />
              <span>有未保存的修改</span>
            </>
          ) : (
            <>
              <span className="inline-block h-2 w-2 rounded-full bg-green-500" />
              <span>已是最新</span>
            </>
          )}
          {showAutoSave && autoSaved && (
            <span className="ml-2 text-gray-400 dark:text-gray-500">
              · 自动保存于 {autoSaved.toLocaleTimeString()}
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          {showResetButton && (
            <button
              type="button"
              onClick={handleReset}
              disabled={!isDirty}
              className="inline-flex items-center gap-1 rounded-lg border border-gray-300 bg-white px-3 py-1 text-xs font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-200 dark:hover:bg-gray-600"
              title="放弃修改，恢复原始"
            >
              ↻ 重置
            </button>
          )}
          {showSaveButton && onSave && (
            <button
              type="button"
              onClick={handleSave}
              disabled={!isDirty}
              className="inline-flex items-center gap-1 rounded-lg bg-brand-600 px-3 py-1 text-xs font-medium text-white transition-colors hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
              title="保存修改"
            >
              💾 保存
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ----------------------------------------------------------------------------
// WYSIWYG Editor using an iframe with designMode = "on"
// ----------------------------------------------------------------------------

function EditableWYSIWYGEditor({
  initialHtml,
  currentHtml,
  placeholder,
  onChange,
  onSelectionChange,
}: {
  initialHtml: string;
  currentHtml: string;
  placeholder: string;
  onChange: (html: string) => void;
  onSelectionChange?: (text: string) => void;
}) {
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const [isFocused, setIsFocused] = useState(false);
  const [isReady, setIsReady] = useState(false);
  const initialBodyRef = useRef<string>("");

  // Build the iframe srcdoc on mount/initial change
  const srcdoc = useMemo(() => {
    if (!initialHtml) {
      // Provide a minimal empty template so the iframe still loads
      return `<!DOCTYPE html><html><head><style>body{padding:20px;font-family:sans-serif;}</style></head><body><p>${placeholder}</p></body></html>`;
    }
    // Embed the FULL HTML document — the original CSS will be loaded as-is.
    // The iframe sandbox gives us perfect style isolation.
    return initialHtml;
  }, [initialHtml, placeholder]);

  // After iframe loads, enable designMode
  const handleIframeLoad = () => {
    const iframe = iframeRef.current;
    if (!iframe) return;
    try {
      const doc = iframe.contentDocument;
      if (!doc) return;

      // Enable rich-text editing
      doc.designMode = "on";

      // Save body innerHTML for reset
      initialBodyRef.current = doc.body?.innerHTML || "";

      // Inject base styles (font-awesome etc. are loaded by the document itself)
      // Add a focus style
      const style = doc.createElement("style");
      style.textContent = `
        body { cursor: text; }
        body:focus, body:focus-within { outline: none; }
        [contenteditable="true"]:focus { outline: none; }
        ::selection { background: rgba(20, 184, 166, 0.3); }
      `;
      doc.head.appendChild(style);

      // Hook input event to capture HTML changes
      doc.addEventListener("input", () => {
        const html = doc.body?.innerHTML || "";
        onChange(html);
      });

      // Selection change for AI rewrite feature
      doc.addEventListener("selectionchange", () => {
        if (!onSelectionChange) return;
        const sel = doc.getSelection();
        const text = sel ? sel.toString() : "";
        onSelectionChange(text);
      });

      // Track focus
      doc.addEventListener("focus", () => setIsFocused(true), true);
      doc.addEventListener("blur", () => setIsFocused(false), true);

      setIsReady(true);
    } catch (e) {
      console.error("Failed to initialize editable iframe:", e);
    }
  };

  // Handle toolbar commands by talking to the iframe document
  const exec = (command: string, value?: string) => {
    const iframe = iframeRef.current;
    if (!iframe) return;
    const doc = iframe.contentDocument;
    if (!doc) return;
    doc.execCommand(command, false, value);
    // Trigger an input event so React state updates
    doc.dispatchEvent(new Event("input", { bubbles: true }));
  };

  const handleLink = () => {
    const iframe = iframeRef.current;
    if (!iframe) return;
    const doc = iframe.contentDocument;
    if (!doc) return;
    const previousUrl = doc.queryCommandValue("createLink");
    const url = window.prompt("链接地址", previousUrl || "https://");
    if (url === null) return; // cancelled
    if (url === "") {
      doc.execCommand("unlink", false);
    } else {
      doc.execCommand("createLink", false, url);
    }
    doc.dispatchEvent(new Event("input", { bubbles: true }));
  };

  // Public reset: rewrite iframe body to the original
  const resetContent = () => {
    const iframe = iframeRef.current;
    if (!iframe) return;
    const doc = iframe.contentDocument;
    if (!doc) return;
    doc.body.innerHTML = initialBodyRef.current;
    doc.dispatchEvent(new Event("input", { bubbles: true }));
  };

  // Expose resetContent via global so external Reset button can use it
  // (we keep it minimal — the parent component calls handleReset which re-renders)
  // The actual reset happens by reloading the iframe srcdoc.

  return (
    <div>
      <div className="flex flex-wrap items-center gap-0.5 rounded-t-lg border border-b-0 border-gray-200 bg-gray-50 px-2 py-1.5 dark:border-gray-600 dark:bg-gray-900">
        <ToolButton title="撤销 (Ctrl+Z)" onClick={() => exec("undo")}>
          <Undo className="h-4 w-4" />
        </ToolButton>
        <ToolButton title="重做 (Ctrl+Y)" onClick={() => exec("redo")}>
          <Redo className="h-4 w-4" />
        </ToolButton>
        <Divider />
        <ToolButton title="一级标题" onClick={() => exec("formatBlock", "h1")}>
          <Heading1 className="h-4 w-4" />
        </ToolButton>
        <ToolButton title="二级标题" onClick={() => exec("formatBlock", "h2")}>
          <Heading2 className="h-4 w-4" />
        </ToolButton>
        <ToolButton title="三级标题" onClick={() => exec("formatBlock", "h3")}>
          <Heading3 className="h-4 w-4" />
        </ToolButton>
        <Divider />
        <ToolButton title="粗体 (Ctrl+B)" onClick={() => exec("bold")}>
          <Bold className="h-4 w-4" />
        </ToolButton>
        <ToolButton title="斜体 (Ctrl+I)" onClick={() => exec("italic")}>
          <Italic className="h-4 w-4" />
        </ToolButton>
        <ToolButton title="下划线 (Ctrl+U)" onClick={() => exec("underline")}>
          <UnderlineIcon className="h-4 w-4" />
        </ToolButton>
        <ToolButton title="删除线" onClick={() => exec("strikeThrough")}>
          <Strikethrough className="h-4 w-4" />
        </ToolButton>
        <Divider />
        <ToolButton title="无序列表" onClick={() => exec("insertUnorderedList")}>
          <List className="h-4 w-4" />
        </ToolButton>
        <ToolButton title="有序列表" onClick={() => exec("insertOrderedList")}>
          <ListOrdered className="h-4 w-4" />
        </ToolButton>
        <ToolButton title="引用" onClick={() => exec("formatBlock", "blockquote")}>
          <Quote className="h-4 w-4" />
        </ToolButton>
        <ToolButton title="分隔线" onClick={() => exec("insertHorizontalRule")}>
          <Minus className="h-4 w-4" />
        </ToolButton>
        <Divider />
        <ToolButton title="添加链接" onClick={handleLink}>
          <LinkIcon className="h-4 w-4" />
        </ToolButton>
        <ToolButton title="清除格式" onClick={() => exec("removeFormat")}>
          <span className="text-[10px] font-bold">Tx</span>
        </ToolButton>
        <Divider />
        <ToolButton
          title="重置为原始"
          onClick={() => {
            if (window.confirm("放弃所有修改，恢复原始内容？")) {
              resetContent();
            }
          }}
        >
          <span className="text-[10px]">↻</span>
        </ToolButton>
      </div>

      <iframe
        ref={iframeRef}
        srcDoc={srcdoc}
        title="Resume Editor"
        onLoad={handleIframeLoad}
        sandbox="allow-same-origin allow-scripts"
        className={`block w-full bg-white transition-colors ${
          isFocused
            ? "border-brand-500 ring-2 ring-brand-500/20"
            : "border-gray-200 dark:border-gray-600"
        }`}
        style={{
          width: "100%",
          height: "700px",
          border: "1px solid",
          borderTop: "none",
          borderRadius: "0 0 0.5rem 0.5rem",
          borderColor: isFocused ? "#14b8a6" : "#e5e7eb",
        }}
      />
      {!isReady && (
        <p className="mt-1 text-center text-xs text-gray-400">Loading editor...</p>
      )}
    </div>
  );
}

interface ToolButtonProps {
  onClick: () => void;
  title: string;
  children: React.ReactNode;
}

function ToolButton({ onClick, title, children }: ToolButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      className="flex h-8 w-8 items-center justify-center rounded text-gray-700 transition-colors hover:bg-gray-100 active:bg-gray-200 dark:text-gray-300 dark:hover:bg-gray-700 dark:active:bg-gray-600"
    >
      {children}
    </button>
  );
}

function Divider() {
  return <div className="mx-1 h-5 w-px bg-gray-200 dark:bg-gray-700" />;
}