import { useEditor, EditorContent, Editor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Underline from "@tiptap/extension-underline";
import Link from "@tiptap/extension-link";
import Placeholder from "@tiptap/extension-placeholder";
import { useEffect, useState } from "react";

interface ResumeEditorProps {
  initialHtml: string;
  onChange: (html: string) => void;
  onSelectionChange?: (selectedText: string) => void;
  placeholder?: string;
  className?: string;
}

export default function ResumeEditor({
  initialHtml,
  onChange,
  onSelectionChange,
  placeholder = "开始编辑你的简历...",
  className = "",
}: ResumeEditorProps) {
  const [isFocused, setIsFocused] = useState(false);

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
    content: initialHtml || "",
    onUpdate: ({ editor }) => {
      onChange(editor.getHTML());
    },
    onSelectionUpdate: ({ editor }) => {
      const { from, to } = editor.state.selection;
      if (from !== to && onSelectionChange) {
        const text = editor.state.doc.textBetween(from, to, " ");
        onSelectionChange(text);
      } else {
        onSelectionChange?.("");
      }
    },
    onFocus: () => setIsFocused(true),
    onBlur: () => setIsFocused(false),
    editorProps: {
      attributes: {
        class:
          "prose prose-sm max-w-none focus:outline-none min-h-[600px] p-6 " + className,
      },
    },
  });

  // Update content if initialHtml changes externally (e.g., style switch)
  useEffect(() => {
    if (editor && initialHtml && editor.getHTML() !== initialHtml) {
      editor.commands.setContent(initialHtml);
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
    <div
      className={`rounded-lg border bg-white transition-colors dark:bg-gray-800 ${
        isFocused
          ? "border-brand-500 ring-2 ring-brand-500/20"
          : "border-gray-200 dark:border-gray-600"
      }`}
    >
      <EditorContent editor={editor} />
    </div>
  );
}

// Re-export Editor type for toolbar use
export type { Editor };
