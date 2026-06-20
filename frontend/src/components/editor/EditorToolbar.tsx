import { Editor } from "@tiptap/react";
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
import { useState } from "react";

interface EditorToolbarProps {
  editor: Editor | null;
  disabled?: boolean;
}

interface ToolButtonProps {
  onClick: () => void;
  active?: boolean;
  disabled?: boolean;
  title: string;
  children: React.ReactNode;
}

function ToolButton({ onClick, active, disabled, title, children }: ToolButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={`flex h-8 w-8 items-center justify-center rounded transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
        active
          ? "bg-brand-100 text-brand-700 dark:bg-brand-900/40 dark:text-brand-300"
          : "text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700"
      }`}
    >
      {children}
    </button>
  );
}

function Divider() {
  return <div className="mx-1 h-5 w-px bg-gray-200 dark:bg-gray-700" />;
}

export default function EditorToolbar({ editor, disabled }: EditorToolbarProps) {
  const [linkUrl, setLinkUrl] = useState("");
  const [showLinkInput, setShowLinkInput] = useState(false);

  if (!editor) {
    return null;
  }

  const handleSetLink = () => {
    if (linkUrl) {
      editor.chain().focus().extendMarkRange("link").setLink({ href: linkUrl }).run();
      setLinkUrl("");
      setShowLinkInput(false);
    } else {
      editor.chain().focus().extendMarkRange("link").unsetLink().run();
      setShowLinkInput(false);
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-0.5 rounded-t-lg border border-b-0 border-gray-200 bg-gray-50 px-2 py-1.5 dark:border-gray-600 dark:bg-gray-900">
      {/* Undo / Redo */}
      <ToolButton
        title="撤销 (Ctrl+Z)"
        onClick={() => editor.chain().focus().undo().run()}
        disabled={disabled || !editor.can().undo()}
      >
        <Undo className="h-4 w-4" />
      </ToolButton>
      <ToolButton
        title="重做 (Ctrl+Shift+Z)"
        onClick={() => editor.chain().focus().redo().run()}
        disabled={disabled || !editor.can().redo()}
      >
        <Redo className="h-4 w-4" />
      </ToolButton>

      <Divider />

      {/* Headings */}
      <ToolButton
        title="一级标题"
        onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()}
        active={editor.isActive("heading", { level: 1 })}
        disabled={disabled}
      >
        <Heading1 className="h-4 w-4" />
      </ToolButton>
      <ToolButton
        title="二级标题"
        onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
        active={editor.isActive("heading", { level: 2 })}
        disabled={disabled}
      >
        <Heading2 className="h-4 w-4" />
      </ToolButton>
      <ToolButton
        title="三级标题"
        onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()}
        active={editor.isActive("heading", { level: 3 })}
        disabled={disabled}
      >
        <Heading3 className="h-4 w-4" />
      </ToolButton>

      <Divider />

      {/* Basic formatting */}
      <ToolButton
        title="粗体 (Ctrl+B)"
        onClick={() => editor.chain().focus().toggleBold().run()}
        active={editor.isActive("bold")}
        disabled={disabled}
      >
        <Bold className="h-4 w-4" />
      </ToolButton>
      <ToolButton
        title="斜体 (Ctrl+I)"
        onClick={() => editor.chain().focus().toggleItalic().run()}
        active={editor.isActive("italic")}
        disabled={disabled}
      >
        <Italic className="h-4 w-4" />
      </ToolButton>
      <ToolButton
        title="下划线 (Ctrl+U)"
        onClick={() => editor.chain().focus().toggleUnderline().run()}
        active={editor.isActive("underline")}
        disabled={disabled}
      >
        <UnderlineIcon className="h-4 w-4" />
      </ToolButton>
      <ToolButton
        title="删除线"
        onClick={() => editor.chain().focus().toggleStrike().run()}
        active={editor.isActive("strike")}
        disabled={disabled}
      >
        <Strikethrough className="h-4 w-4" />
      </ToolButton>
      <ToolButton
        title="行内代码"
        onClick={() => editor.chain().focus().toggleCode().run()}
        active={editor.isActive("code")}
        disabled={disabled}
      >
        <Code className="h-4 w-4" />
      </ToolButton>

      <Divider />

      {/* Lists */}
      <ToolButton
        title="无序列表"
        onClick={() => editor.chain().focus().toggleBulletList().run()}
        active={editor.isActive("bulletList")}
        disabled={disabled}
      >
        <List className="h-4 w-4" />
      </ToolButton>
      <ToolButton
        title="有序列表"
        onClick={() => editor.chain().focus().toggleOrderedList().run()}
        active={editor.isActive("orderedList")}
        disabled={disabled}
      >
        <ListOrdered className="h-4 w-4" />
      </ToolButton>
      <ToolButton
        title="引用"
        onClick={() => editor.chain().focus().toggleBlockquote().run()}
        active={editor.isActive("blockquote")}
        disabled={disabled}
      >
        <Quote className="h-4 w-4" />
      </ToolButton>
      <ToolButton
        title="分隔线"
        onClick={() => editor.chain().focus().setHorizontalRule().run()}
        disabled={disabled}
      >
        <Minus className="h-4 w-4" />
      </ToolButton>

      <Divider />

      {/* Link */}
      {showLinkInput ? (
        <div className="flex items-center gap-1 rounded bg-white px-1 py-0.5 dark:bg-gray-800">
          <input
            type="url"
            value={linkUrl}
            onChange={(e) => setLinkUrl(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                handleSetLink();
              } else if (e.key === "Escape") {
                setShowLinkInput(false);
                setLinkUrl("");
              }
            }}
            placeholder="https://..."
            className="h-7 w-40 rounded border border-gray-300 px-2 text-xs focus:border-brand-500 focus:outline-none dark:border-gray-600 dark:bg-gray-700 dark:text-white"
            autoFocus
          />
          <button
            type="button"
            onClick={handleSetLink}
            className="rounded bg-brand-600 px-2 py-1 text-xs text-white hover:bg-brand-700"
          >
            确定
          </button>
          <button
            type="button"
            onClick={() => {
              setShowLinkInput(false);
              setLinkUrl("");
            }}
            className="rounded bg-gray-200 px-2 py-1 text-xs text-gray-700 hover:bg-gray-300 dark:bg-gray-600 dark:text-gray-200"
          >
            取消
          </button>
        </div>
      ) : (
        <>
          <ToolButton
            title="添加链接"
            onClick={() => {
              const previousUrl = editor.getAttributes("link").href;
              setLinkUrl(previousUrl || "https://");
              setShowLinkInput(true);
            }}
            active={editor.isActive("link")}
            disabled={disabled}
          >
            <LinkIcon className="h-4 w-4" />
          </ToolButton>
          {editor.isActive("link") && (
            <ToolButton
              title="移除链接"
              onClick={() => editor.chain().focus().unsetLink().run()}
              disabled={disabled}
            >
              <Unlink className="h-4 w-4" />
            </ToolButton>
          )}
        </>
      )}
    </div>
  );
}
