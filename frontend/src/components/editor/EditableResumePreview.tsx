import { useState, useEffect, useRef } from "react";
import { useEditor, EditorContent, Editor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Underline from "@tiptap/extension-underline";
import Link from "@tiptap/extension-link";
import Placeholder from "@tiptap/extension-placeholder";
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
import ResumeEditor from "./ResumeEditor";
import EditorToolbar from "./EditorToolbar";

interface EditableResumePreviewProps {
  initialHtml: string;
  onSave?: (html: string) => void;
  onChange?: (html: string) => void;
  onSelectionChange?: (text: string) => void;
  onReset?: () => void;
  placeholder?: string;
  className?: string;
  // Optional: enable the internal "Save" button (calls onSave)
  showSaveButton?: boolean;
  // Optional: enable the internal "Reset" button (calls onReset)
  showResetButton?: boolean;
  // Optional: show auto-save indicator
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

  // Detect changes
  useEffect(() => {
    setIsDirty(currentHtml !== initialHtml);
  }, [currentHtml, initialHtml]);

  // Auto-save with debounce
  useEffect(() => {
    if (!isDirty || !showAutoSave) return;
    if (debounceRef.current) {
      window.clearTimeout(debounceRef.current);
    }
    debounceRef.current = window.setTimeout(() => {
      // Auto-save to localStorage (do not trigger onSave callback here)
      try {
        const key = `resume_edit_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
        localStorage.setItem(key, currentHtml);
        // Keep only last 5 autosaves
        const allKeys = Object.keys(localStorage).filter((k) => k.startsWith("resume_edit_"));
        if (allKeys.length > 5) {
          allKeys
            .sort()
            .slice(0, allKeys.length - 5)
            .forEach((k) => localStorage.removeItem(k));
        }
        setAutoSaved(new Date());
      } catch (e) {
        // localStorage may be full or disabled
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
      <EditablePreviewWithToolbar
        initialHtml={initialHtml}
        currentHtml={currentHtml}
        placeholder={placeholder}
        onChange={handleChange}
        onSelectionChange={onSelectionChange}
      />

      {/* Status / Action bar */}
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

// Internal component that uses TipTap hooks (must be its own component to use useEditor)
function EditablePreviewWithToolbar({
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
  const [isFocused, setIsFocused] = useState(false);
  const lastInitialRef = useRef(initialHtml);

  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: { levels: [1, 2, 3] },
      }),
      Underline,
      Link.configure({
        openOnClick: false,
        autolink: true,
        HTMLAttributes: {
          class: "text-brand-600 underline hover:text-brand-700",
        },
      }),
      Placeholder.configure({
        placeholder,
        showOnlyWhenEditable: true,
      }),
    ],
    content: currentHtml || "",
    onUpdate: ({ editor }) => {
      onChange(editor.getHTML());
    },
    onSelectionUpdate: ({ editor }) => {
      if (!onSelectionChange) return;
      const { from, to } = editor.state.selection;
      if (from !== to) {
        const text = editor.state.doc.textBetween(from, to, " ");
        onSelectionChange(text);
      } else {
        onSelectionChange("");
      }
    },
    onFocus: () => setIsFocused(true),
    onBlur: () => setIsFocused(false),
    editorProps: {
      attributes: {
        class:
          "prose prose-sm max-w-none focus:outline-none min-h-[600px] p-6",
      },
    },
  });

  // Update content when initialHtml changes externally (e.g., style switch reset)
  useEffect(() => {
    if (editor && initialHtml !== lastInitialRef.current) {
      editor.commands.setContent(initialHtml || "");
      lastInitialRef.current = initialHtml;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialHtml]);

  if (!editor) {
    return (
      <div className="flex h-[600px] items-center justify-center text-sm text-gray-500">
        Loading editor...
      </div>
    );
  }

  return (
    <div>
      <EditorToolbar editor={editor} />
      <div
        className={`overflow-hidden rounded-b-lg border border-t-0 bg-white transition-colors dark:bg-gray-800 ${
          isFocused
            ? "border-brand-500 ring-2 ring-brand-500/20"
            : "border-gray-200 dark:border-gray-600"
        }`}
      >
        <EditorContent editor={editor} />
      </div>
    </div>
  );
}
