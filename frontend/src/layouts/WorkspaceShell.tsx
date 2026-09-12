import { useRef, useState, type CSSProperties, type KeyboardEvent, type PointerEvent, type ReactNode } from "react";
import { GripVertical } from "lucide-react";
import type { Lang } from "../i18n";
import AssistantPane from "../assistant/AssistantPane";

interface Props { page: string; lang: Lang; children: ReactNode; }

const ASSISTANT_WIDTH_KEY = "buping_assistant_width_percent";
const DEFAULT_ASSISTANT_WIDTH = 33.33;
const MIN_ASSISTANT_WIDTH = 25;
const MAX_ASSISTANT_WIDTH = 65;

function clampWidth(value: number): number {
  return Math.min(MAX_ASSISTANT_WIDTH, Math.max(MIN_ASSISTANT_WIDTH, value));
}

export default function WorkspaceShell({ page, lang, children }: Props) {
  const [mobileTab, setMobileTab] = useState<"assistant" | "workspace">("workspace");
  const [assistantWidth, setAssistantWidth] = useState(() => {
    if (typeof window === "undefined") return DEFAULT_ASSISTANT_WIDTH;
    const saved = Number(window.localStorage.getItem(ASSISTANT_WIDTH_KEY));
    return Number.isFinite(saved) && saved > 0 ? clampWidth(saved) : DEFAULT_ASSISTANT_WIDTH;
  });
  const splitRef = useRef<HTMLDivElement | null>(null);

  const updateWidth = (next: number) => {
    const value = clampWidth(next);
    setAssistantWidth(value);
    window.localStorage.setItem(ASSISTANT_WIDTH_KEY, value.toFixed(2));
  };

  const startResize = (event: PointerEvent<HTMLButtonElement>) => {
    const split = splitRef.current;
    if (!split) return;
    event.preventDefault();
    const previousCursor = document.body.style.cursor;
    const previousSelection = document.body.style.userSelect;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";

    const onMove = (moveEvent: globalThis.PointerEvent) => {
      const rect = split.getBoundingClientRect();
      if (!rect.width) return;
      updateWidth(((moveEvent.clientX - rect.left) / rect.width) * 100);
    };
    const stop = () => {
      document.body.style.cursor = previousCursor;
      document.body.style.userSelect = previousSelection;
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", stop);
      window.removeEventListener("pointercancel", stop);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", stop);
    window.addEventListener("pointercancel", stop);
  };

  const resizeWithKeyboard = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    updateWidth(assistantWidth + (event.key === "ArrowLeft" ? -2 : 2));
  };

  const splitStyle = { "--assistant-width": `${assistantWidth}%` } as CSSProperties;

  return (
    <div className="h-full min-h-0">
      <div className="mb-3 grid grid-cols-2 rounded-lg bg-gray-100 p-1 lg:hidden dark:bg-gray-800">
        <button onClick={() => setMobileTab("assistant")} className={`rounded-md py-2 text-sm ${mobileTab === "assistant" ? "bg-white shadow dark:bg-gray-700" : "text-gray-500"}`}>{lang === "zh" ? "不平" : "Buping"}</button>
        <button onClick={() => setMobileTab("workspace")} className={`rounded-md py-2 text-sm ${mobileTab === "workspace" ? "bg-white shadow dark:bg-gray-700" : "text-gray-500"}`}>工作区</button>
      </div>
      <div ref={splitRef} className="workspace-split h-[calc(100%-3.25rem)] min-h-0 min-w-0 lg:h-full" style={splitStyle}>
        <div className={`${mobileTab === "assistant" ? "block" : "hidden lg:block"} min-w-0 lg:sticky lg:top-3 lg:self-start`}>
          <AssistantPane page={page} lang={lang} />
        </div>
        <button
          type="button"
          role="separator"
          aria-label={lang === "zh" ? "调整对话框宽度" : "Resize assistant pane"}
          aria-orientation="vertical"
          aria-valuemin={MIN_ASSISTANT_WIDTH}
          aria-valuemax={MAX_ASSISTANT_WIDTH}
          aria-valuenow={Math.round(assistantWidth)}
          title={lang === "zh" ? "拖动调整宽度，双击恢复三分之一" : "Drag to resize; double-click to reset"}
          onPointerDown={startResize}
          onKeyDown={resizeWithKeyboard}
          onDoubleClick={() => updateWidth(DEFAULT_ASSISTANT_WIDTH)}
          className="workspace-divider group relative cursor-col-resize items-center justify-center focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
        >
          <span className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-gray-200 transition-colors group-hover:bg-brand-400 group-focus-visible:bg-brand-500 dark:bg-gray-700" />
          <span className="relative z-10 rounded-full border border-gray-200 bg-white py-2 text-gray-400 shadow-sm transition-colors group-hover:border-brand-300 group-hover:text-brand-600 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-500">
            <GripVertical className="h-4 w-4" />
          </span>
        </button>
        <div className={`${mobileTab === "workspace" ? "block" : "hidden lg:block"} h-full min-h-0 min-w-0 overflow-hidden`}>{children}</div>
      </div>
    </div>
  );
}
